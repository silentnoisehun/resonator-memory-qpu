"""
plan.py — Sorsolt bitek, lezárt JSON, véletlen áramkör-sorrend
Máté + Maya (Sesame), 2026-11-11
"""

import hashlib, json, time
import numpy as np
from pathlib import Path


class Plan:
    def __init__(self, seed: int, phase: str):
        self.seed  = seed
        self.phase = phase
        self.rng   = np.random.default_rng(seed)
        self._sealed: dict = {}

    # ── Bit-sorsolás ──────────────────────────────────────────────────────────

    def draw_bits(self, label: str, n: int) -> list:
        bits = self.rng.integers(0, 2, size=n).tolist()
        self._sealed[label] = [int(b) for b in bits]
        return bits

    # ── Áramkör-sorrend ───────────────────────────────────────────────────────

    def shuffle_indices(self, n_circuits: int) -> list:
        """Visszaad egy véletlen permutációt [0..n_circuits-1]-re."""
        order = self.rng.permutation(n_circuits).tolist()
        self._sealed["shuffle_order"] = order
        return order

    # ── Lezárás / megnyitás ───────────────────────────────────────────────────

    def seal(self, path: str) -> str:
        blob = json.dumps({
            "seed":      self.seed,
            "phase":     self.phase,
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data":      self._sealed,
        }, indent=2, sort_keys=True)
        sha = hashlib.sha256(blob.encode()).hexdigest()
        Path(path).write_text(blob, encoding="utf-8")
        print(f"[plan] sealed → {path}  SHA={sha[:16]}…")
        return sha

    @staticmethod
    def unseal(path: str, expected_sha: str) -> dict:
        blob     = Path(path).read_text(encoding="utf-8")
        computed = hashlib.sha256(blob.encode()).hexdigest()
        if computed != expected_sha:
            raise ValueError(
                f"Sealed plan hash MISMATCH\n"
                f"  expected: {expected_sha}\n"
                f"  computed: {computed}"
            )
        return json.loads(blob)["data"]

    @staticmethod
    def hash_circuit_list(circs) -> str:
        """Áramkörlista hash-e (a keverés előtti sorrendé)."""
        names = json.dumps([c.name for c in circs], sort_keys=True)
        return hashlib.sha256(names.encode()).hexdigest()


def shuffle_circuits(circs: list, order: list) -> list:
    """Áramköröket a megadott sorrend szerint kever."""
    return [circs[i] for i in order]
