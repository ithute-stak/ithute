#!/usr/bin/env sh

# Load a Docker Compose dotenv file without executing it as shell code.
#
# Docker Compose supports dotenv syntax that is not necessarily valid or safe
# to source with POSIX sh (for example: APP_NAME=Mailbox DNS). Production
# secrets can also contain shell metacharacters. Use Compose's own parser, then
# export each parsed key/value pair literally into the current shell.
load_dotenv() {
  env_file="${1:-.env}"
  [ -f "$env_file" ] || {
    echo "Missing dotenv file: $env_file" >&2
    return 1
  }

  command -v docker >/dev/null 2>&1 || {
    echo "Docker is required to parse $env_file" >&2
    return 1
  }

  parsed_env="$(mktemp)"
  if ! docker compose --env-file "$env_file" config --environment > "$parsed_env"; then
    rm -f "$parsed_env"
    echo "Failed to parse dotenv file: $env_file" >&2
    return 1
  fi

  # Do not use `IFS='=' read -r key value` here. POSIX sh discards delimiter
  # characters while field-splitting, which corrupts values such as padded
  # base64/Fernet keys ending in `=`. Read each complete line and split only at
  # the first equals sign so the value is preserved byte-for-byte.
  while IFS= read -r line || [ -n "${line:-}" ]; do
    [ -n "${line:-}" ] || continue
    case "$line" in
      *=*) ;;
      *)
        rm -f "$parsed_env"
        echo "Invalid environment entry parsed from $env_file" >&2
        return 1
        ;;
    esac

    key=${line%%=*}
    value=${line#*=}
    case "$key" in
      ""|*[!A-Za-z0-9_]*|[0-9]*)
        rm -f "$parsed_env"
        echo "Invalid environment variable name parsed from $env_file: $key" >&2
        return 1
        ;;
    esac
    export "$key=$value"
  done < "$parsed_env"

  rm -f "$parsed_env"
}
