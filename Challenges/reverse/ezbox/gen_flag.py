"""Generate encrypted flag for Hanoi CTF challenge."""
import sys
from flag import xxtea_encrypt, xxtea_decrypt, hash_level_state, derive_key, TOTAL_LEVELS
from levels import load_level_file, collect_all_context_paths


def file_for_context(ctx: str) -> str:
    """Map context path to level file. 'h10/1/0' -> 'h0', 'h10' -> 'h10'."""
    last = ctx.rsplit('/', 1)[-1]
    return last if last.startswith('h') else f'h{last}'


def main():
    if len(sys.argv) < 2:
        print('Usage: python gen_flag.py "flag{your_flag_here}"')
        sys.exit(1)

    flag_text = sys.argv[1]
    contexts = collect_all_context_paths()
    assert len(contexts) == TOTAL_LEVELS, f'{len(contexts)} != {TOTAL_LEVELS}'

    print(f'Generating encrypted flag for: {flag_text}')
    print(f'Total contexts: {len(contexts)}')
    print()

    completed_hashes = {}
    for ctx in sorted(contexts):
        file_id = file_for_context(ctx)
        terrain, _, _ = load_level_file(file_id)
        goals = sorted(f'{x},{y}' for (x, y), c in terrain.items() if c in '=_')
        goals_str = ';'.join(goals)
        completed_hashes[ctx] = hash_level_state(ctx, goals_str)

    key = derive_key(completed_hashes)
    print(f'Derived key (hex): {key.hex()}')

    flag_bytes = flag_text.encode()
    pad_len = (4 - len(flag_bytes) % 4) % 4
    padded = flag_bytes + b'\x00' * pad_len
    encrypted = xxtea_encrypt(padded, key)

    print(f'ENCRYPTED_FLAG = bytes.fromhex(\'{encrypted.hex()}\')')
    print()

    decrypted = xxtea_decrypt(encrypted, key)
    decrypted_text = decrypted.decode().rstrip('\x00')
    print(f'Decryption check: {decrypted_text}')
    assert decrypted_text == flag_text
    print('OK.')
    print()
    print('Copy ENCRYPTED_FLAG into flag.py')


if __name__ == '__main__':
    main()
