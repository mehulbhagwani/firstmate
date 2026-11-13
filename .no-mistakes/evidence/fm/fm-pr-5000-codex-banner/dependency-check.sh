#!/usr/bin/env bash
set -eu
LAB=$(mktemp -d "$PWD/.nm-install-check.XXXXXX")
trap 'rm -rf "$LAB"' EXIT
cp -R bin "$LAB/bin"
for condition in missing unreadable; do
  if [ "$condition" = missing ]; then
    rm "$LAB/bin/fm-composer-pi-adapter.sh"
  else
    cp bin/fm-composer-pi-adapter.sh "$LAB/bin/fm-composer-pi-adapter.sh"
    chmod 000 "$LAB/bin/fm-composer-pi-adapter.sh"
  fi
  for backend in tmux herdr zellij orca cmux paseo rex t3code tern hc; do
    set +e
    output=$(bash -c '. "$1/bin/fm-backend.sh"; fm_backend_source "$2"' check "$LAB" "$backend" 2>&1)
    rc=$?
    set -e
    printf '%s adapter / %s: status=%s\n%s\n' "$condition" "$backend" "$rc" "$output"
    [ "$rc" -ne 0 ]
  done
  chmod 600 "$LAB/bin/fm-composer-pi-adapter.sh" 2>/dev/null || true
done
