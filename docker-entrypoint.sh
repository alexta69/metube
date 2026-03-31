#!/bin/sh

set -eu

fail() {
    echo "Error: $*" >&2
    exit 1
}

require_numeric() {
    name="$1"
    value="$2"
    case "$value" in
        ''|*[!0-9]*)
            fail "${name} must be numeric"
            ;;
    esac
}

require_octal_umask() {
    case "$1" in
        [0-7][0-7][0-7]|[0-7][0-7][0-7][0-7])
            ;;
        *)
            fail "UMASK must be a 3 or 4 digit octal value"
            ;;
    esac
}

ensure_directory_access_current_user() {
    path="$1"
    label="$2"
    [ -d "$path" ] || fail "${label} does not exist: ${path}"
    [ -r "$path" ] || fail "${label} is not readable: ${path}"
    [ -w "$path" ] || fail "${label} is not writable: ${path}"
    [ -x "$path" ] || fail "${label} is not traversable: ${path}"
}

ensure_directory_access_as_user() {
    user_spec="$1"
    shift
    if ! gosu "$user_spec" sh -eu -c '
        for dir_path in "$@"; do
            [ -d "$dir_path" ] || exit 10
            [ -r "$dir_path" ] || exit 11
            [ -w "$dir_path" ] || exit 12
            [ -x "$dir_path" ] || exit 13
        done
    ' sh "$@"; then
        fail "Configured directories are not accessible for ${user_spec}"
    fi
}

: "${PUID:=1000}"
: "${PGID:=1000}"
: "${UMASK:=022}"
: "${DOWNLOAD_DIR:?DOWNLOAD_DIR must be set}"
: "${STATE_DIR:?STATE_DIR must be set}"
: "${TEMP_DIR:?TEMP_DIR must be set}"

PUID="${UID:-$PUID}"
PGID="${GID:-$PGID}"

require_numeric "PUID" "$PUID"
require_numeric "PGID" "$PGID"
require_octal_umask "$UMASK"

echo "Setting umask to ${UMASK}"
umask "$UMASK"

echo "Creating download directory (${DOWNLOAD_DIR}), state directory (${STATE_DIR}), and temp dir (${TEMP_DIR})"
mkdir -p "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"

if [ "$(id -u)" -eq 0 ] && [ "$(id -g)" -eq 0 ]; then
    if [ "${PUID}" -eq 0 ]; then
        echo "Warning: it is not recommended to run as root user, please check your setting of the PUID/PGID (or legacy UID/GID) environment variables"
    fi
    if [ "${CHOWN_DIRS:-true}" != "false" ]; then
        echo "Changing ownership of data directories to ${PUID}:${PGID}"
        chown -R "${PUID}:${PGID}" "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"
    fi
    ensure_directory_access_as_user "${PUID}:${PGID}" "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"
    echo "Starting BgUtils POT Provider"
    gosu "${PUID}:${PGID}" bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
    echo "Running MeTube as user ${PUID}:${PGID}"
    exec gosu "${PUID}:${PGID}" python3 app/main.py
fi

echo "User set by docker; running MeTube as $(id -u):$(id -g)"
ensure_directory_access_current_user "${DOWNLOAD_DIR}" "DOWNLOAD_DIR"
ensure_directory_access_current_user "${STATE_DIR}" "STATE_DIR"
ensure_directory_access_current_user "${TEMP_DIR}" "TEMP_DIR"
echo "Starting BgUtils POT Provider"
bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
exec python3 app/main.py
