#!/usr/bin/env python3
"""Generate ES256 key pair for JWT signing.

Generates a P-256 ECDSA key pair and outputs them in PEM format
for use in environment variables.

Usage:
    python scripts/generate_keys.py

Output:
    Prints private and public keys in PEM format.
    Copy these to your .env file.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_es256_keypair() -> tuple[str, str]:
    """Generate an ES256 (P-256 ECDSA) key pair.

    Returns:
        Tuple of (private_key_pem, public_key_pem)
    """
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1())

    # Serialize private key to PEM
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Serialize public key to PEM
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def main() -> None:
    """Generate and print ES256 key pair."""
    private_key, public_key = generate_es256_keypair()

    print("=" * 60)
    print("ES256 Key Pair Generated")
    print("=" * 60)
    print()
    print("Add these to your .env file:")
    print()
    print("# JWT Private Key (keep secret!)")
    print("# For .env file, use single line with \\n for newlines:")
    print()

    # Convert to single-line format for .env
    private_single = private_key.replace("\n", "\\n")
    print(f'JWT_PRIVATE_KEY="{private_single}"')
    print()
    print("# JWT Public Key (can be shared for verification)")
    public_single = public_key.replace("\n", "\\n")
    print(f'JWT_PUBLIC_KEY="{public_single}"')
    print()
    print("=" * 60)
    print()
    print("Multi-line format (for reference):")
    print()
    print("Private Key:")
    print(private_key)
    print("Public Key:")
    print(public_key)


if __name__ == "__main__":
    main()
