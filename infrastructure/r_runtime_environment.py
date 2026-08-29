import os


def build_r_subprocess_environment(site_library_path=None):
    """Build a deterministic environment for the bundled R runtime."""
    env = os.environ.copy()

    blocked = {
        "R_HOME",
        "R_ARCH",
        "R_ENVIRON",
        "R_ENVIRON_USER",
        "R_PROFILE",
        "R_PROFILE_USER",
        "R_LIBS",
        "R_LIBS_SITE",
        "R_LIBS_USER",
    }
    for key in list(env):
        upper = key.upper()
        if upper in blocked:
            env.pop(key, None)
            continue
        if os.name == "nt" and (upper == "LANG" or upper.startswith("LC_")):
            # POSIX locale names such as C.UTF-8 can break R's path decoding
            # when the bundled runtime sits below a non-ASCII directory.
            env.pop(key, None)

    if site_library_path is not None:
        site_library = str(site_library_path)
        env["R_LIBS"] = site_library
        env["R_LIBS_SITE"] = site_library
        env["R_LIBS_USER"] = site_library

    return env
