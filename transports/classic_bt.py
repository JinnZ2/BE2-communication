"""
classic_bt.py — Classic Bluetooth Accessibility Transport

Repurposes Classic Bluetooth profiles (AVRCP, HFP, A2DP) to push
emergency alerts to consumer devices that deaf and hard-of-hearing
users already own — car dashboards, smart speakers with screens,
fitness watches, LED speakers, hearing aids.

Why this matters:
  Deaf users can't hear emergency sirens, voice alerts, or phone calls.
  But they're surrounded by Bluetooth devices with screens and haptic
  motors. This transport turns every nearby display and vibration motor
  into an emergency notification channel — no app install required.

Three channels, one purpose:

  AVRCP (Audio/Video Remote Control Profile)
    - Every Bluetooth audio device supports AVRCP metadata.
    - Track title / artist / album fields displayed on screens.
    - Car dashboards, smart speakers, fitness trackers all show these.
    - We hijack these fields to display emergency text alerts.
    - "Track title" = alert message, "Artist" = sender, "Album" = priority.

  HFP (Hands-Free Profile)
    - The AT command channel carries small text strings (separate from audio).
    - +CIEV indicator events can signal state changes.
    - Nearly every phone supports HFP for car kits.
    - Low-bandwidth but universally available data path.

  A2DP (Advanced Audio Distribution Profile)
    - Audio stream to connected speakers/headphones.
    - Encode haptic alert patterns as specific audio waveforms.
    - LED speakers that pulse to music will pulse to emergency patterns.
    - Hearing aids with Bluetooth can render alerts as tonal patterns.

Hardware: Any phone with Bluetooth 2.1+ (virtually all phones since ~2008).
No pairing required for AVRCP metadata broadcast on many devices.

Real implementation uses `pybluez` or platform-specific APIs.
For development, uses file-based simulator (same as all other transports).

Usage (simulator):
    t = ClassicBTTransport(device_id="phone_01")

Usage (real hardware — requires pybluez):
    t = ClassicBTTransport(device_id="phone_01", use_hardware=True)

Released CC0.
"""

import os
import json
import math
import time
import struct
import threading
import tempfile
from typing import Optional, Callable
from collections import defaultdict

from core.message import Message
from core.transport import Transport


# ── Constants ──────────────────────────────────

# AVRCP metadata field limits (Bluetooth spec)
AVRCP_TITLE_MAX = 255      # track title
AVRCP_ARTIST_MAX = 255     # artist name
AVRCP_ALBUM_MAX = 255      # album name

# HFP AT command max payload
HFP_AT_MAX = 127            # typical AT command line limit

# Alert priority levels (mapped to AVRCP album field)
ALERT_SOS = "SOS"
ALERT_URGENT = "URGENT"
ALERT_INFO = "INFO"
ALERT_LOCATION = "LOCATION"

# Haptic patterns — encoded as (frequency_hz, duration_ms, pause_ms) tuples
# These generate recognizable audio waveforms on A2DP speakers
HAPTIC_SOS = [
    # ... --- ... in vibration/audio
    (800, 100, 50), (800, 100, 50), (800, 100, 150),   # S: 3 short
    (400, 300, 50), (400, 300, 50), (400, 300, 150),   # O: 3 long
    (800, 100, 50), (800, 100, 50), (800, 100, 300),   # S: 3 short
]
HAPTIC_URGENT = [
    (600, 200, 100), (600, 200, 100), (600, 200, 400),  # 3 medium pulses
]
HAPTIC_INFO = [
    (500, 150, 300),  # single gentle pulse
]
HAPTIC_LOCATION = [
    (700, 100, 100), (500, 200, 300),  # short-long (like a ping)
]

# How many times to repeat an SOS broadcast for reliability
SOS_REPEAT_COUNT = 3
SOS_REPEAT_INTERVAL = 1.0  # seconds between repeats


# ── AVRCP Alert Formatting ────────────────────

class AVRCPAlert:
    """
    Format emergency alerts as AVRCP metadata fields.

    On a car dashboard or smart speaker screen, this shows up as:
      Track: ⚠ SOS — Trapped in basement, 123 Oak St
      Artist: phone_alice
      Album: SOS | 14:32

    On a fitness watch:
      Now Playing: ⚠ SOS — Trapped in basement
    """

    # Unicode symbols that render on most screens (no emoji — wider compat)
    SYMBOL_SOS = "\u26a0"       # ⚠ warning sign
    SYMBOL_URGENT = "\u2757"    # ❗ exclamation
    SYMBOL_INFO = "\u2139"      # ℹ info
    SYMBOL_LOCATION = "\u25cb"  # ○ circle (like a map pin)

    PRIORITY_SYMBOLS = {
        ALERT_SOS: SYMBOL_SOS,
        ALERT_URGENT: SYMBOL_URGENT,
        ALERT_INFO: SYMBOL_INFO,
        ALERT_LOCATION: SYMBOL_LOCATION,
    }

    @staticmethod
    def format_title(priority: str, text: str) -> str:
        """Format alert text for AVRCP track title field."""
        symbol = AVRCPAlert.PRIORITY_SYMBOLS.get(priority, "")
        title = f"{symbol} {priority} \u2014 {text}" if symbol else f"{priority} \u2014 {text}"
        return title[:AVRCP_TITLE_MAX]

    @staticmethod
    def format_artist(sender: str) -> str:
        """Sender ID goes in the artist field."""
        return sender[:AVRCP_ARTIST_MAX]

    @staticmethod
    def format_album(priority: str, timestamp: float = 0.0) -> str:
        """Priority + time in album field."""
        t = time.strftime("%H:%M", time.localtime(timestamp or time.time()))
        return f"{priority} | {t}"[:AVRCP_ALBUM_MAX]

    @staticmethod
    def format_metadata(priority: str, sender: str, text: str,
                        timestamp: float = 0.0) -> dict:
        """Full AVRCP metadata dict ready for broadcast."""
        return {
            "title": AVRCPAlert.format_title(priority, text),
            "artist": AVRCPAlert.format_artist(sender),
            "album": AVRCPAlert.format_album(priority, timestamp),
        }

    @staticmethod
    def parse_metadata(metadata: dict) -> Optional[dict]:
        """
        Extract alert info from AVRCP metadata.
        Returns dict with priority, sender, text, time — or None if not an alert.
        """
        title = metadata.get("title", "")
        artist = metadata.get("artist", "")
        album = metadata.get("album", "")

        # Check if this looks like one of our alerts
        for priority, symbol in AVRCPAlert.PRIORITY_SYMBOLS.items():
            prefix = f"{symbol} {priority} \u2014 "
            if title.startswith(prefix):
                text = title[len(prefix):]
                time_str = ""
                if " | " in album:
                    time_str = album.split(" | ", 1)[1]
                return {
                    "priority": priority,
                    "sender": artist,
                    "text": text,
                    "time": time_str,
                }
        return None


# ── HFP Text Channel ─────────────────────────

class HFPChannel:
    """
    Use the HFP AT command channel as a text data path.

    HFP defines several AT commands that carry text-like data.
    We use +CIEV (indicator event) and custom +BRSF extensions
    to push short alert strings through the hands-free channel.

    This works because car kits and hearing aids with HFP
    already process these commands — we just encode our
    alerts in a format they can display or act on.
    """

    @staticmethod
    def encode_alert(priority: str, text: str, sender: str = "") -> str:
        """Encode an alert as an AT command string."""
        # Use AT+CSMS (custom service message) format
        # Truncate to HFP line limit
        sender_part = f":{sender}" if sender else ""
        cmd = f"+CSMS: {priority}{sender_part},{text}"
        return cmd[:HFP_AT_MAX]

    @staticmethod
    def decode_alert(at_cmd: str) -> Optional[dict]:
        """Decode an alert from AT command format."""
        if not at_cmd.startswith("+CSMS: "):
            return None
        content = at_cmd[7:]  # strip "+CSMS: "
        # Parse "PRIORITY:sender,text" or "PRIORITY,text"
        if "," not in content:
            return None
        header, text = content.split(",", 1)
        if ":" in header:
            priority, sender = header.split(":", 1)
        else:
            priority = header
            sender = ""
        return {"priority": priority, "sender": sender, "text": text}

    @staticmethod
    def encode_location(lat: float, lon: float) -> str:
        """Encode GPS coordinates as a compact AT command."""
        # +CLOC: lat,lon (6 decimal places = ~0.11m accuracy)
        return f"+CLOC: {lat:.6f},{lon:.6f}"

    @staticmethod
    def decode_location(at_cmd: str) -> Optional[tuple[float, float]]:
        """Decode GPS coordinates from AT command."""
        if not at_cmd.startswith("+CLOC: "):
            return None
        try:
            parts = at_cmd[7:].split(",")
            return float(parts[0]), float(parts[1])
        except (ValueError, IndexError):
            return None


# ── A2DP Haptic Patterns ──────────────────────

class HapticEncoder:
    """
    Encode emergency alerts as audio waveforms for A2DP streaming.

    When played on:
    - LED speakers: pulsing light patterns visible to deaf users
    - Vibration speakers: tactile alerts
    - Hearing aids: tonal patterns within aided frequency range
    - Bone conduction devices: vibration alerts

    Patterns use distinct frequency/duration combos so they're
    recognizable even on low-quality speakers.
    """

    PATTERNS = {
        ALERT_SOS: HAPTIC_SOS,
        ALERT_URGENT: HAPTIC_URGENT,
        ALERT_INFO: HAPTIC_INFO,
        ALERT_LOCATION: HAPTIC_LOCATION,
    }

    @staticmethod
    def generate_tone(freq_hz: int, duration_ms: int,
                      sample_rate: int = 8000) -> list[int]:
        """
        Generate a simple sine wave tone as 8-bit PCM samples.
        Lightweight — no numpy required.
        """
        n_samples = int(sample_rate * duration_ms / 1000)
        samples = []
        for i in range(n_samples):
            t = i / sample_rate
            # Sine wave, scaled to 8-bit unsigned (0-255)
            value = int(128 + 127 * math.sin(2 * math.pi * freq_hz * t))
            samples.append(max(0, min(255, value)))
        return samples

    @staticmethod
    def generate_silence(duration_ms: int,
                         sample_rate: int = 8000) -> list[int]:
        """Generate silence as 8-bit PCM samples."""
        n_samples = int(sample_rate * duration_ms / 1000)
        return [128] * n_samples

    @classmethod
    def encode_pattern(cls, priority: str,
                       sample_rate: int = 8000) -> list[int]:
        """
        Encode a haptic/alert pattern as PCM audio samples.
        Returns list of 8-bit unsigned PCM values.
        """
        pattern = cls.PATTERNS.get(priority, cls.PATTERNS[ALERT_INFO])
        samples: list[int] = []
        for freq_hz, duration_ms, pause_ms in pattern:
            samples.extend(cls.generate_tone(freq_hz, duration_ms, sample_rate))
            samples.extend(cls.generate_silence(pause_ms, sample_rate))
        return samples

    @classmethod
    def encode_pattern_bytes(cls, priority: str,
                             sample_rate: int = 8000) -> bytes:
        """Encode pattern as raw bytes (8-bit unsigned PCM)."""
        return bytes(cls.encode_pattern(priority, sample_rate))

    @staticmethod
    def pattern_duration_ms(priority: str) -> int:
        """Calculate total duration of a pattern in milliseconds."""
        pattern = HapticEncoder.PATTERNS.get(
            priority, HapticEncoder.PATTERNS[ALERT_INFO]
        )
        return sum(d + p for _, d, p in pattern)


# ── Classic BT Backends ───────────────────────

class ClassicBTBackend:
    """Abstract Classic Bluetooth interface."""

    def send_avrcp(self, metadata: dict) -> bool: ...
    def send_hfp(self, at_command: str) -> bool: ...
    def send_a2dp(self, audio_data: bytes) -> bool: ...
    def read(self, timeout: float = 1.0) -> Optional[dict]: ...
    def close(self): ...
    def is_available(self) -> bool: ...


class RealClassicBT(ClassicBTBackend):
    """
    Real Classic Bluetooth using pybluez or platform APIs.

    AVRCP: Uses MPRIS (Linux) or platform media session API
    HFP: Uses rfcomm serial channel
    A2DP: Uses PulseAudio/ALSA bluetooth sink

    Requires platform-specific setup. Falls back to simulator.
    """

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._available = False
        try:
            import bluetooth  # noqa: F401  (pybluez)
            self._available = True
        except ImportError:
            pass

    def send_avrcp(self, metadata: dict) -> bool:
        if not self._available:
            return False
        # Real AVRCP: write to MPRIS D-Bus or platform media session
        # dbus-send --dest=org.mpris.MediaPlayer2.emergency ...
        return False  # placeholder

    def send_hfp(self, at_command: str) -> bool:
        if not self._available:
            return False
        # Real HFP: write to rfcomm channel
        return False  # placeholder

    def send_a2dp(self, audio_data: bytes) -> bool:
        if not self._available:
            return False
        # Real A2DP: write PCM to bluetooth audio sink
        return False  # placeholder

    def read(self, timeout: float = 1.0) -> Optional[dict]:
        if not self._available:
            return None
        return None  # placeholder

    def close(self):
        pass

    def is_available(self) -> bool:
        return self._available


class SimulatedClassicBT(ClassicBTBackend):
    """
    File-based Classic BT simulator for development.
    All instances sharing the same channel_dir can see each other.
    Simulates AVRCP metadata display and HFP text channel.
    """

    def __init__(self, device_id: str, channel_dir: Optional[str] = None):
        self.device_id = device_id
        self.channel_dir = channel_dir or os.path.join(
            tempfile.gettempdir(), "classic_bt_sim"
        )
        os.makedirs(self.channel_dir, exist_ok=True)
        self._seen: set[str] = set()

    def send_avrcp(self, metadata: dict) -> bool:
        return self._write_file("avrcp", metadata)

    def send_hfp(self, at_command: str) -> bool:
        return self._write_file("hfp", {"at": at_command})

    def send_a2dp(self, audio_data: bytes) -> bool:
        return self._write_file("a2dp", {
            "samples": len(audio_data),
            "duration_ms": len(audio_data) * 1000 // 8000,
        })

    def read(self, timeout: float = 1.0) -> Optional[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                files = sorted(os.listdir(self.channel_dir))
                for fname in files:
                    if fname in self._seen:
                        continue
                    if self.device_id in fname:
                        self._seen.add(fname)
                        continue
                    fpath = os.path.join(self.channel_dir, fname)
                    self._seen.add(fname)
                    with open(fpath, "r") as f:
                        return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
            time.sleep(0.05)
        return None

    def close(self):
        pass

    def is_available(self) -> bool:
        return True

    def _write_file(self, profile: str, data: dict) -> bool:
        try:
            fname = f"{int(time.time() * 10000)}_{self.device_id}_{profile}.json"
            fpath = os.path.join(self.channel_dir, fname)
            payload = {"profile": profile, "sender": self.device_id, "data": data}
            with open(fpath, "w") as f:
                json.dump(payload, f)
            return True
        except OSError:
            return False


# ── Classic BT Accessibility Transport ────────

class ClassicBTTransport(Transport):
    """
    Classic Bluetooth transport for accessible emergency alerts.

    Pushes emergency information to devices deaf users already own:
    - Car dashboards (AVRCP track title = alert text)
    - Smart speakers with screens (AVRCP metadata display)
    - Fitness watches (AVRCP "now playing" notification)
    - Hearing aids (A2DP tonal patterns)
    - LED speakers (A2DP audio → visual light patterns)

    This is a broadcast-to-existing-devices layer. It doesn't replace
    the BLE mesh for phone-to-phone data — it pushes simplified alerts
    to whatever consumer Bluetooth hardware is nearby, making emergency
    information accessible without requiring any app installation on
    the receiving device.

    Features:
    - AVRCP metadata alerts (text on any Bluetooth display)
    - HFP AT command text channel (data over voice link)
    - A2DP haptic patterns (vibration/light on speakers)
    - Multi-channel broadcast (all three profiles simultaneously)
    - SOS repeat for reliability
    - Dedup on incoming alerts
    """

    def __init__(self, device_id: str = "classic_bt_device",
                 use_hardware: bool = False,
                 channel_dir: Optional[str] = None,
                 enable_avrcp: bool = True,
                 enable_hfp: bool = True,
                 enable_a2dp: bool = True):
        self.device_id = device_id
        self.enable_avrcp = enable_avrcp
        self.enable_hfp = enable_hfp
        self.enable_a2dp = enable_a2dp

        # Select backend
        if use_hardware:
            self._backend = RealClassicBT(device_id)
            if not self._backend.is_available():
                self._backend = SimulatedClassicBT(device_id, channel_dir)
        else:
            self._backend = SimulatedClassicBT(device_id, channel_dir)

        # Dedup
        self._seen_ids: dict[str, float] = {}
        self._dedup_window = 300  # seconds

        # Stats
        self._avrcp_sent = 0
        self._hfp_sent = 0
        self._a2dp_sent = 0

        # Threading
        self._callback: Optional[Callable[[Message], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()

    @property
    def transport_name(self) -> str:
        backend = "hw" if isinstance(self._backend, RealClassicBT) else "sim"
        return f"ClassicBT({backend}:{self.device_id})"

    # ── Transport ABC implementation ──────────

    def send(self, msg: Message, target: str = "") -> bool:
        """Send alert across all enabled Classic BT profiles."""
        return self._broadcast_alert(msg)

    def broadcast(self, msg: Message) -> int:
        """Broadcast to all nearby Classic BT devices."""
        return 1 if self._broadcast_alert(msg) else 0

    def receive(self) -> Optional[Message]:
        """Not used directly — use start_listening."""
        return None

    def start_listening(self, callback: Callable[[Message], None]):
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop_listening(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)

    def close(self):
        self._running = False
        self._backend.close()

    # ── High-level alert methods ──────────────

    def send_sos(self, sender: str, text: str,
                 lat: float = 0.0, lon: float = 0.0) -> bool:
        """
        Broadcast an SOS alert on all channels with repeat.

        This is the critical accessibility method. It pushes the SOS
        to every nearby Bluetooth screen and haptic device:
        - Car dashboard shows: "⚠ SOS — Trapped in basement"
        - LED speaker pulses: ... --- ... (SOS pattern)
        - Hearing aid plays: recognizable tonal SOS pattern
        """
        success = False
        for _ in range(SOS_REPEAT_COUNT):
            with self._send_lock:
                # AVRCP: text on screens
                if self.enable_avrcp:
                    metadata = AVRCPAlert.format_metadata(
                        ALERT_SOS, sender, text)
                    if self._backend.send_avrcp(metadata):
                        self._avrcp_sent += 1
                        success = True

                # HFP: text via AT command
                if self.enable_hfp:
                    at_cmd = HFPChannel.encode_alert(ALERT_SOS, text, sender)
                    if self._backend.send_hfp(at_cmd):
                        self._hfp_sent += 1
                        success = True
                    # Also send location if available
                    if lat != 0.0 or lon != 0.0:
                        loc_cmd = HFPChannel.encode_location(lat, lon)
                        self._backend.send_hfp(loc_cmd)

                # A2DP: haptic/audio SOS pattern
                if self.enable_a2dp:
                    audio = HapticEncoder.encode_pattern_bytes(ALERT_SOS)
                    if self._backend.send_a2dp(audio):
                        self._a2dp_sent += 1
                        success = True

            if _ < SOS_REPEAT_COUNT - 1:
                time.sleep(SOS_REPEAT_INTERVAL)
        return success

    def send_location(self, sender: str, lat: float, lon: float,
                      note: str = "") -> bool:
        """Share location on all channels."""
        with self._send_lock:
            success = False
            text = f"Location: {lat:.4f}, {lon:.4f}"
            if note:
                text += f" ({note})"

            if self.enable_avrcp:
                metadata = AVRCPAlert.format_metadata(
                    ALERT_LOCATION, sender, text)
                if self._backend.send_avrcp(metadata):
                    self._avrcp_sent += 1
                    success = True

            if self.enable_hfp:
                loc_cmd = HFPChannel.encode_location(lat, lon)
                if self._backend.send_hfp(loc_cmd):
                    self._hfp_sent += 1
                    success = True

            if self.enable_a2dp:
                audio = HapticEncoder.encode_pattern_bytes(ALERT_LOCATION)
                if self._backend.send_a2dp(audio):
                    self._a2dp_sent += 1
                    success = True

            return success

    def send_supply_alert(self, sender: str, supplies: dict) -> bool:
        """Announce available supplies on screen-capable devices."""
        items = ", ".join(f"{k}: {v}" for k, v in supplies.items())
        text = f"Supplies available: {items}"

        with self._send_lock:
            success = False
            if self.enable_avrcp:
                metadata = AVRCPAlert.format_metadata(
                    ALERT_INFO, sender, text)
                if self._backend.send_avrcp(metadata):
                    self._avrcp_sent += 1
                    success = True

            if self.enable_hfp:
                at_cmd = HFPChannel.encode_alert(ALERT_INFO, text, sender)
                if self._backend.send_hfp(at_cmd):
                    self._hfp_sent += 1
                    success = True

            return success

    # ── Internal ──────────────────────────────

    def _broadcast_alert(self, msg: Message) -> bool:
        """Convert an agent Message to Classic BT alerts and broadcast."""
        # Determine priority from message verb/topic
        if msg.verb == "STUCK":
            priority = ALERT_SOS
        elif msg.verb == "STATE" and msg.topic == "location":
            priority = ALERT_LOCATION
        elif msg.verb == "OFFER":
            priority = ALERT_INFO
        else:
            priority = ALERT_URGENT if msg.verb == "QUERY" else ALERT_INFO

        # Extract text from body
        if isinstance(msg.body, dict):
            text = msg.body.get("message", msg.body.get("text", str(msg.body)))
        elif isinstance(msg.body, str):
            text = msg.body
        else:
            text = str(msg.body) if msg.body else ""

        # Mark seen
        self._seen_ids[msg.msg_id] = time.time()

        with self._send_lock:
            success = False

            # AVRCP
            if self.enable_avrcp:
                metadata = AVRCPAlert.format_metadata(
                    priority, msg.sender, text, msg.timestamp)
                if self._backend.send_avrcp(metadata):
                    self._avrcp_sent += 1
                    success = True

            # HFP
            if self.enable_hfp:
                at_cmd = HFPChannel.encode_alert(priority, text, msg.sender)
                if self._backend.send_hfp(at_cmd):
                    self._hfp_sent += 1
                    success = True

            # A2DP haptic pattern for SOS/urgent only (avoid alert fatigue)
            if self.enable_a2dp and priority in (ALERT_SOS, ALERT_URGENT):
                audio = HapticEncoder.encode_pattern_bytes(priority)
                if self._backend.send_a2dp(audio):
                    self._a2dp_sent += 1
                    success = True

            return success

    def _listen_loop(self):
        """Listen for incoming Classic BT alerts from other devices."""
        while self._running:
            data = self._backend.read(timeout=0.5)
            if data is None:
                continue

            try:
                msg = self._reconstruct_message(data)
                if msg and msg.msg_id not in self._seen_ids:
                    self._seen_ids[msg.msg_id] = time.time()
                    if self._callback:
                        self._callback(msg)
            except Exception:
                pass  # graceful degradation — malformed data gets ignored

            self._cleanup_dedup()

    def _reconstruct_message(self, data: dict) -> Optional[Message]:
        """Reconstruct an agent Message from Classic BT profile data."""
        profile = data.get("profile", "")
        sender = data.get("sender", "unknown")
        inner = data.get("data", {})

        if profile == "avrcp":
            parsed = AVRCPAlert.parse_metadata(inner)
            if parsed:
                return Message(
                    verb="STUCK" if parsed["priority"] == ALERT_SOS else "STATE",
                    sender=parsed["sender"] or sender,
                    body={"text": parsed["text"], "priority": parsed["priority"]},
                    topic="accessibility_alert",
                )

        elif profile == "hfp":
            at_cmd = inner.get("at", "")
            parsed = HFPChannel.decode_alert(at_cmd)
            if parsed:
                verb = "STUCK" if parsed["priority"] == ALERT_SOS else "STATE"
                return Message(
                    verb=verb,
                    sender=parsed["sender"] or sender,
                    body={"text": parsed["text"], "priority": parsed["priority"]},
                    topic="accessibility_alert",
                )
            loc = HFPChannel.decode_location(at_cmd)
            if loc:
                return Message(
                    verb="STATE",
                    sender=sender,
                    body={"lat": loc[0], "lon": loc[1]},
                    topic="location",
                )

        return None

    def _cleanup_dedup(self):
        """Expire old dedup entries."""
        now = time.time()
        expired = [k for k, t in self._seen_ids.items()
                   if now - t > self._dedup_window]
        for k in expired:
            del self._seen_ids[k]

    @property
    def accessibility_stats(self) -> dict:
        """Return stats about accessibility alert delivery."""
        return {
            "device_id": self.device_id,
            "avrcp_alerts_sent": self._avrcp_sent,
            "hfp_commands_sent": self._hfp_sent,
            "a2dp_patterns_sent": self._a2dp_sent,
            "total_alerts": self._avrcp_sent + self._hfp_sent + self._a2dp_sent,
            "unique_messages_seen": len(self._seen_ids),
            "profiles_enabled": {
                "avrcp": self.enable_avrcp,
                "hfp": self.enable_hfp,
                "a2dp": self.enable_a2dp,
            },
        }
