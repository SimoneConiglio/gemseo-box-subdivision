# Copyright 2026 Simone Coniglio
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""Configuration of the Sphinx documentation."""

from __future__ import annotations

from importlib.metadata import version as get_version
from os import environ
from pathlib import Path
from shutil import copyfile
from sysconfig import get_paths

REPOSITORY_URL = "https://github.com/SimoneConiglio/gemseo-box-subdivision"
SITE_URL = "https://simoneconiglio.github.io/gemseo-box-subdivision"

# Two builds are published, the released one at the root of the site and the
# integration branch under /dev/, so a page has to say which one is being read:
# the development build documents code that is not in any release.
CHANNEL = environ.get("DOCS_CHANNEL", "local")
DEVELOPMENT = CHANNEL == "dev"

project = "gemseo-box-subdivision"
author = "Simone Coniglio"
copyright = "2026, Simone Coniglio"  # noqa: A001
release = get_version("gemseo-box-subdivision")
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
    "sphinx_design",
]

myst_enable_extensions = ["dollarmath", "amsmath", "colon_fence", "deflist"]
myst_heading_anchors = 3

autosummary_generate = True
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

# Fetching the inventories requires network access, and their failure cannot be
# suppressed, so it would fail a -W build offline. They are enabled explicitly,
# by the workflow that publishes the documentation.
intersphinx_mapping = (
    {
        "python": ("https://docs.python.org/3", None),
        "numpy": ("https://numpy.org/doc/stable", None),
        "scipy": ("https://docs.scipy.org/doc/scipy", None),
        "gemseo": ("https://gemseo.readthedocs.io/en/stable", None),
    }
    if environ.get("SPHINX_INTERSPHINX") == "1"
    else {}
)
intersphinx_disabled_reftypes = ["*"]
intersphinx_timeout = 10

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = "gemseo-box-subdivision"
html_show_sourcelink = False

# Pages without children would otherwise show an empty section navigation.
html_sidebars = {"index": [], "installation": [], "changelog": []}

html_theme_options = {
    "github_url": REPOSITORY_URL,
    "icon_links": [
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/gemseo-box-subdivision/",
            "icon": "fa-solid fa-box",
        },
    ],
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "navbar_align": "left",
    "show_prev_next": True,
    "show_toc_level": 2,
    "use_edit_page_button": True,
    "header_links_before_dropdown": 4,
    "footer_start": ["copyright"],
    "footer_end": ["theme-version"],
}
if DEVELOPMENT:
    html_theme_options["announcement"] = (
        "This is the documentation of the <strong>development branch</strong>, "
        "which describes code that is in no release. "
        f'The released documentation is <a href="{SITE_URL}/">here</a>.'
    )
html_context = {
    "github_user": "SimoneConiglio",
    "github_repo": "gemseo-box-subdivision",
    "github_version": "develop" if DEVELOPMENT else "main",
    "doc_path": "docs",
    "default_mode": "auto",
}


# MathJax is served from the documentation itself rather than from a CDN, so
# that the equations render on a network that blocks third-party CDNs, and from
# a local build. The bundle comes from the sphinx-mathjax-offline distribution,
# whose directory name is not a valid identifier, hence it cannot be used as an
# extension and only its files are read.
MATHJAX_BUNDLE = "tex-svg-full.js"
"""The self-contained MathJax bundle, whose SVG output needs no web font."""


def _find_mathjax_bundle() -> Path | None:
    """Return the path to the MathJax bundle, if it is installed.

    Returns:
        The path to the bundle, or ``None`` when it is not installed.
    """
    bundle = (
        Path(get_paths()["purelib"])
        / "sphinx-mathjax-offline"
        / "static"
        / "mathjax"
        / MATHJAX_BUNDLE
    )
    return bundle if bundle.is_file() else None


def setup(app):  # noqa: ANN001, ANN201
    """Serve MathJax from the documentation when its bundle is installed.

    Args:
        app: The Sphinx application.
    """
    bundle = _find_mathjax_bundle()
    if bundle is None:
        # Fall back on the CDN configured by Sphinx rather than break the build.
        return

    app.connect(
        "builder-inited",
        lambda application: setattr(
            application.config, "mathjax_path", f"mathjax/{MATHJAX_BUNDLE}"
        ),
    )
    app.connect(
        "build-finished",
        lambda application, exception: (
            _copy_mathjax_bundle(application, bundle) if exception is None else None
        ),
    )


def _copy_mathjax_bundle(app, bundle) -> None:  # noqa: ANN001
    """Copy the MathJax bundle next to the other static files.

    Args:
        app: The Sphinx application.
        bundle: The path to the bundle.
    """
    directory = Path(app.outdir, "_static", "mathjax")
    directory.mkdir(parents=True, exist_ok=True)
    copyfile(bundle, directory / MATHJAX_BUNDLE)


nitpicky = False
# The inventories are unreachable when building without network access,
# which must not fail a -W build.
suppress_warnings = ["myst.header"]
