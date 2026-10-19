"""Start Aivatar's local API. This entrypoint never submits a paid generation."""

from pipeline.sidecar import main


if __name__ == "__main__":
    main()
