#!/usr/bin/env bash
# Minify the site's own JS/CSS with esbuild: foo.js -> foo.min.js, next to the source.
# Run after every change to a .js/.css file under staticfiles/ and commit the
# .min.* output (the Docker image has no node/esbuild, it ships what is committed).
# Templates load the .min.* files through {% static_v %}, which appends a content
# hash, so there is no version number to bump.
set -euo pipefail

cd "$(dirname "$0")/staticfiles"

if ! command -v esbuild >/dev/null; then
    echo "esbuild not found in PATH" >&2
    exit 1
fi

# Oldest syntax the output must run on; also stops esbuild from "upgrading" syntax.
# (A browser list can't be used for JS: esbuild refuses to lower destructuring for
# the Safari versions it flags as buggy.)
JS_TARGET="es2020"
CSS_TARGET="chrome80,edge80,firefox78,safari13.1"

# js/d3/ is vendored and already ships its own d3.min.js.
find . -type f \( -name '*.js' -o -name '*.css' \) \
    ! -name '*.min.js' ! -name '*.min.css' ! -path './js/d3/*' -print0 |
while IFS= read -r -d '' src; do
    out="${src%.*}.min.${src##*.}"
    case "$src" in
        *.js) target="$JS_TARGET" ;;
        *)    target="$CSS_TARGET" ;;
    esac
    esbuild "$src" --minify --target="$target" --log-level=warning --outfile="$out"
    printf '%-32s %7d -> %7d bytes\n' "${src#./}" "$(wc -c <"$src")" "$(wc -c <"$out")"
done
