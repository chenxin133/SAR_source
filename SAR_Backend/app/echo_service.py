from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import numpy as np
from PIL import Image


MAX_ECHO_BYTES = 64 * 1024 * 1024
BAND_FREQUENCIES_GHZ = {"C": 5.3, "X": 9.6, "Ku": 15.0, "Ka": 35.0}
SAMPLE_RATE_HZ = 120_000_000.0
BANDWIDTH_HZ = 80_000_000.0
PRF_HZ = 2000.0


def read_header(path: Path, byte_order: str = "little") -> tuple[int, int]:
    if byte_order not in ("little", "big"):
        raise ValueError("字节序必须为 little 或 big")
    size = path.stat().st_size
    if size < 8 or size > MAX_ECHO_BYTES:
        raise ValueError("dat 文件必须包含 8 字节文件头，且不能超过 64 MiB")
    with path.open("rb") as stream:
        na, nr = struct.unpack("<ii" if byte_order == "little" else ">ii", stream.read(8))
    if na <= 0 or nr <= 0:
        raise ValueError("Na（脉冲数）和 Nr（采样点数）必须为正的 int32")
    expected = 8 + na * (4 + nr * 4)
    if size != expected:
        raise ValueError(f"dat 长度不匹配：Na={na}, Nr={nr}，应为 {expected} 字节，实际 {size} 字节")
    return na, nr


def open_echo(path: Path, byte_order: str = "little") -> np.memmap:
    na, nr = read_header(path, byte_order)
    endian = "<" if byte_order == "little" else ">"
    dtype = np.dtype([("gate", endian + "u4"), ("iq", endian + "u2", (nr, 2))])
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(na,))


def create_preview(path: Path, output: Path, byte_order: str, iq_offset: int) -> dict:
    records = open_echo(path, byte_order)
    try:
        na, nr = len(records), records.dtype["iq"].shape[0]
        rows = np.linspace(0, na - 1, min(na, 256), dtype=int)
        columns = np.linspace(0, nr - 1, min(nr, 512), dtype=int)
        iq = records["iq"][rows[:, None], columns].astype(np.float32) - iq_offset
        magnitude = np.hypot(iq[..., 0], iq[..., 1])
        db = 20 * np.log10(np.maximum(magnitude, 1))
        low, high = float(db.min()), float(db.max())
        normalized = (db - low) / max(high - low, 1)
        rgb = np.stack((normalized, normalized ** 0.65, 0.25 + 0.65 * (1 - normalized)), axis=-1)
        Image.fromarray(np.uint8(np.clip(rgb, 0, 1) * 255)).save(output)
        return {"na": na, "nr": nr, "gate_min": int(records["gate"].min()),
                "gate_max": int(records["gate"].max())}
    finally:
        records._mmap.close()


def pulse_preview(path: Path, byte_order: str, iq_offset: int, pulse: int) -> dict:
    records = open_echo(path, byte_order)
    try:
        na, nr = len(records), records.dtype["iq"].shape[0]
        if pulse < 0 or pulse >= na:
            raise ValueError(f"脉冲索引必须在 0 至 {na - 1} 之间")
        indices = np.linspace(0, nr - 1, min(nr, 1024), dtype=int)
        raw = records["iq"][pulse, indices].astype(np.int32)
        centered = raw - iq_offset
        return {"pulse": pulse, "igate": int(records["gate"][pulse]), "indices": indices.tolist(),
                "i": raw[:, 0].tolist(), "q": raw[:, 1].tolist(),
                "magnitude": np.hypot(centered[:, 0], centered[:, 1]).tolist(),
                "phase": np.arctan2(centered[:, 1], centered[:, 0]).tolist()}
    finally:
        records._mmap.close()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def simulate_echo(path: Path, *, na: int, nr: int, seed: int, noise_std: float,
                  gate_start: int, frequency_band: str = "X") -> None:
    """Deterministic baseband LFM point-target demo; uint16 offset-binary I/Q."""
    rng = np.random.default_rng(seed)
    samples = np.arange(nr, dtype=np.float64)
    pulse_samples = max(4.0, nr / 8)
    carrier_hz = BAND_FREQUENCIES_GHZ[frequency_band] * 1e9
    speed_of_light = 299_792_458.0
    with path.open("wb") as stream:
        stream.write(struct.pack("<ii", na, nr))
        for pulse in range(na):
            azimuth = (pulse - (na - 1) / 2) / max(na, 1)
            signal = np.zeros(nr, dtype=np.complex128)
            slow_time = (pulse - (na - 1) / 2) / PRF_HZ
            for position, amplitude, velocity in ((0.25, 11000, 0.2), (0.52, 8000, -0.35), (0.76, 6000, 0.5)):
                center = (nr * position + nr * 0.04 * azimuth ** 2
                          + 2 * velocity * slow_time * SAMPLE_RATE_HZ / speed_of_light)
                delay = samples - center
                envelope = np.where(np.abs(delay) <= pulse_samples / 2,
                                    0.5 * (1 + np.cos(2 * np.pi * delay / pulse_samples)), 0)
                distance = (gate_start + center) * speed_of_light / (2 * SAMPLE_RATE_HZ)
                phase = (np.pi * (BANDWIDTH_HZ / SAMPLE_RATE_HZ) * delay ** 2 / pulse_samples
                         - 4 * np.pi * carrier_hz * distance / speed_of_light)
                signal += amplitude * envelope * np.exp(1j * phase)
            noise = rng.normal(0, noise_std, (nr, 2))
            iq = np.stack((signal.real, signal.imag), axis=-1) + noise + 32768
            encoded = np.clip(np.rint(iq), 0, 65535).astype("<u2")
            stream.write(struct.pack("<I", gate_start))
            stream.write(encoded.tobytes())
