"""
keygen.py  ──  USO ESCLUSIVO SVILUPPATORE
Genera il Serial Key per un dato Machine ID cliente.

Esegui:  python keygen.py
"""

import hashlib
import hmac
import sys

# ── Deve essere identica a license_manager.py ────────────────────────────────
SECRET_KEY = b"oF8bIDALzBU9S8tt6sArNsnDQWlu8hPLHlnyh82WTBchgTNYknYEyA"
# ─────────────────────────────────────────────────────────────────────────────


def genera_serial(machine_id: str) -> str:
    machine_id = machine_id.strip().upper()
    sig = hmac.new(SECRET_KEY, machine_id.encode(), hashlib.sha256).hexdigest().upper()
    return "-".join(sig[i:i+6] for i in range(0, 30, 6))


def main():
    print("=" * 52)
    print("  KEYGEN  –  Solo per uso interno sviluppatore")
    print("=" * 52)

    if len(sys.argv) == 2:
        # Uso: python keygen.py <MACHINE_ID>
        machine_id = sys.argv[1]
    else:
        machine_id = input("\nInserisci il Machine ID del cliente:\n> ").strip()

    if not machine_id:
        print("Errore: Machine ID vuoto.")
        sys.exit(1)

    serial = genera_serial(machine_id)

    print()
    print(f"  Machine ID : {machine_id.upper()}")
    print(f"  Serial Key : {serial}")
    print()


if __name__ == "__main__":
    main()
