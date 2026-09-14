from __future__ import annotations


def main() -> None:
    print(
        "CyberSLM-Crypto model toolkit\n\n"
        "Commands:\n"
        "  cyberslm-train      Inspect, validate, and fine-tune reviewed datasets\n"
        "  cyberslm-eval       Run model, safety, and RAG evaluations\n"
        "  cyberslm-benchmark  Benchmark supported inference runtimes\n"
        "  cyberslm-knowledge  Build and verify the optional RAG corpus\n\n"
        "See README.md and training/README.md for the universal model workflow."
    )


if __name__ == "__main__":
    main()
