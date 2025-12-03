"""
Library version info.
"""

import platform as platform_library

library_name = "sharing-api"
version = "0.1.0"
platform = platform_library.platform()
python_version = platform_library.python_version()
user_agent = f"{library_name}-v{version}-{platform}-py{python_version}"
