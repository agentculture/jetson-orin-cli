"""Injectable command executor for the privileged window verbs.

An :data:`Exec` takes ``(argv, stdin)`` and returns ``(returncode, stdout,
stderr)``, or ``None`` when ``argv[0]`` is not installed. Tests pass fakes, so no
suite ever runs sudo, jetson_clocks, nvpmodel or a cache drop.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
from typing import Callable, Optional, Sequence

Exec = Callable[[Sequence[str], Optional[str]], Optional[tuple[int, str, str]]]

DEFAULT_TIMEOUT = 30.0


def default_exec(argv: Sequence[str], stdin: Optional[str] = None):
    exe = shutil.which(argv[0])
    if exe is None:
        return None
    try:
        proc = subprocess.run(  # nosec B603
            [exe, *argv[1:]],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, proc.stdout, proc.stderr
