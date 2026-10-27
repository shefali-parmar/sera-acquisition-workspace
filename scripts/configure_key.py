"""Save an operator API key privately without a text editor or a model request."""

from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key


def main() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    print("Paste your OpenAI API key, then press Enter.")
    print("The key will be hidden: no characters or dots will appear while you paste.")
    try:
        key = getpass("API key: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. No settings changed.")
        return
    if not key.startswith("sk-") or len(key) < 20 or any(char.isspace() for char in key):
        print(
            "Not saved: this does not look like an OpenAI API key. Copy the secret key, not its name."
        )
        return
    # dotenv replaces only the named setting and preserves other operator configuration.
    set_key(path, "OPENAI_API_KEY", key)
    if not dotenv_values(path).get("OPENAI_MODEL"):
        set_key(path, "OPENAI_MODEL", "gpt-4.1-mini")
    path.chmod(0o600)
    print("Saved successfully to SERA/.env. The key was not displayed or tested against the API.")


if __name__ == "__main__":
    main()
