import random
import string

def generate_strong_password(length: int = 16) -> str:
    """
    Generates a strong random password containing:
    - Uppercase letters
    - Lowercase letters
    - Digits
    - Punctuation (symbols)

    Ensures at least one of each category is present.
    """
    if length < 8:
        length = 8

    # Character sets
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*" # safer subset of punctuation

    # Ensure at least one of each
    password = [
        random.choice(upper),
        random.choice(lower),
        random.choice(digits),
        random.choice(symbols)
    ]

    # Fill the rest
    all_chars = upper + lower + digits + symbols
    for _ in range(length - 4):
        password.append(random.choice(all_chars))

    # Shuffle to avoid predictable patterns
    random.shuffle(password)

    return "".join(password)
