import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_NAME = "Qwen/Qwen3-0.6B"


def main() -> None:
    print("Avvio test...", flush=True)

    print("CUDA disponibile:", torch.cuda.is_available(), flush=True)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA non disponibile")

    print("GPU:", torch.cuda.get_device_name(0), flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    print("Tokenizer caricato", flush=True)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        dtype=torch.float16,
    ).to("cuda")

    model.eval()

    print("Modello caricato", flush=True)
    print("Model device:", next(model.parameters()).device, flush=True)

    messages = [
        {
            "role": "user",
            "content": "Rispondi in una frase: perché i test automatici sono utili?",
        }
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

    print("Input device:", inputs["input_ids"].device, flush=True)
    print("Inizio generazione...", flush=True)

    start = time.perf_counter()

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    elapsed = time.perf_counter() - start

    generated_tokens = output[0, inputs["input_ids"].shape[1]:]
    answer = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=True,
    )

    print("\nRisposta:", flush=True)
    print(answer, flush=True)

    print(f"\nTempo generazione: {elapsed:.2f} secondi", flush=True)
    print(
        f"VRAM allocata: {torch.cuda.memory_allocated() / 1024**3:.2f} GB",
        flush=True,
    )
    print(
        f"Picco VRAM: {torch.cuda.max_memory_allocated() / 1024**3:.2f} GB",
        flush=True,
    )

    print("Test completato.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERRORE: {type(exc).__name__}: {exc}", flush=True)
        raise