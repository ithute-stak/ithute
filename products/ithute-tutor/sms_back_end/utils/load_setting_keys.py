def load_keys(settings):
    # Ensure both or none
    if bool(settings.JWT_PRIVATE_KEY) != bool(settings.JWT_PUBLIC_KEY):
        raise ValueError("Both JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be set together")

    # ✅ Use env keys (production)
    if settings.JWT_PRIVATE_KEY and settings.JWT_PUBLIC_KEY:
        try:
            private_key = settings.JWT_PRIVATE_KEY.encode("utf-8")
            public_key = settings.JWT_PUBLIC_KEY.encode("utf-8")
            return private_key, public_key

        except AttributeError:
            # Happens if value is not a string (e.g. None or wrong type)
            raise ValueError("JWT keys must be valid strings")

        except UnicodeEncodeError as e:
            # Rare, but good to catch
            raise ValueError(f"Encoding error in JWT keys: {str(e)}")

        except Exception as e:
            raise ValueError(f"Unexpected encoding error: {str(e)}")

    # ✅ Fallback to files (development)
    if not settings.JWT_PRIVATE_KEY_PATH or not settings.JWT_PUBLIC_KEY_PATH:
        raise ValueError("Key paths are required for local environment")

    try:
        with open(settings.JWT_PRIVATE_KEY_PATH, "rb") as f:
            private_key = f.read()

        with open(settings.JWT_PUBLIC_KEY_PATH, "rb") as f:
            public_key = f.read()

        return private_key, public_key

    except FileNotFoundError as e:
        raise ValueError(f"Key file not found: {str(e)}")

    except PermissionError:
        raise ValueError("Permission denied when reading key files")

    except Exception as e:
        raise ValueError(f"Failed to load key files: {str(e)}")