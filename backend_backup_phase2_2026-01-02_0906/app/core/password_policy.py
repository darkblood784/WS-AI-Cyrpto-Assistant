import re

def validate_password(password: str, email: str) -> None:
    """
    Raises ValueError with a clear message if password is not acceptable.
    """
    pw = password or ""
    em = (email or "").strip().lower()

    if len(pw) < 10:
        raise ValueError("Password must be at least 10 characters long.")
    if len(pw) > 128:
        raise ValueError("Password must be at most 128 characters long.")
    if not re.search(r"[A-Z]", pw):
        raise ValueError("Password must include at least 1 uppercase letter.")
    if not re.search(r"[a-z]", pw):
        raise ValueError("Password must include at least 1 lowercase letter.")
    if not re.search(r"[0-9]", pw):
        raise ValueError("Password must include at least 1 number.")
    if not re.search(r"[^A-Za-z0-9]", pw):
        raise ValueError("Password must include at least 1 symbol (e.g. !@#$).")

    # Block obvious email-derived passwords (prevents 'whales123!' type)
    if "@" in em:
        local, _, domain = em.partition("@")
        parts = [p for p in re.split(r"[._\-+]", local) if p] + [domain]
        low_pw = pw.lower()
        for p in parts:
            if len(p) >= 3 and p in low_pw:
                raise ValueError("Password must not contain parts of your email address.")
