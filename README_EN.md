# Web-Novel Continuation + Proofreading LoRA (Qwen3-4B)

English | [中文](README.md)

A QLoRA adapter for **Qwen3-4B-Instruct-2507**. One LoRA does two tasks on Chinese web novels:

- **Proofreading**: fixes typos (look-alike characters, 的/地/得), punctuation, anti-piracy junk characters, pinyin substitutions and `**` masking
- **Continuation**: continues a passage in the same style

## Results

| Metric | Result |
|---|---|
| Continuation perplexity | 27.55 → **20.32** (-26.2%) |
| Proofreading fix rate | **74.9%** (light 70.9% / medium 79.3% / heavy 73.5%) |
| Proofreading character accuracy | **99.71%**; false-edit rate on clean text 0.0001 |

Measured on books held out from training. Full reports are in `work/08_eval/`.

## Quick start

```bash
# 1. Environment (Python 3.12)
uv venv venv-train --python 3.12
uv pip install --python ./venv-train/bin/python torch --index-url https://download.pytorch.org/whl/cu126  # /whl/cpu for CPU
uv pip install --python ./venv-train/bin/python "transformers==5.6.0" "peft==0.18.1" accelerate bitsandbytes modelscope

# 2. Base model + LoRA weights
./venv-train/bin/modelscope download --model Qwen/Qwen3-4B-Instruct-2507 --local_dir models/Qwen3-4B-Instruct-2507
curl -L -o work/07_train/std/adapter_model.safetensors \
  https://github.com/ArchitektSpeer/novel-lora-qwen3-4b/releases/download/v1.0/adapter_model.safetensors

# 3. Proofread
./venv-train/bin/python scripts/demo_proofread.py --input dirty.txt --output fixed.txt
./venv-train/bin/python scripts/demo_proofread.py --web          # web UI, run `pip install gradio` first

# 4. Continue a passage
./venv-train/bin/python scripts/t6_infer_demo.py --adapter work/07_train/std \
  --mode continue --prompt-file prefix.txt --max-new 800
```

- With a GPU, the model loads in 4-bit and needs about 4 GB of VRAM. Without one, it switches to CPU bf16 automatically and needs about 10 GB of RAM.
- Long text is split into chunks of up to 1,200 characters and proofread one chunk at a time.
- Do not install the `kernels` package. It is incompatible with transformers 5.6.

## Proofreading example

A 718-character passage with 12 injected errors, run CPU-only on an i5-8250U in about 7 minutes:

| Error type | Original | Corrupted | Model output | |
|---|---|---|---|---|
| Look-alike char | 会**在**东荒 | 会**再** | 会**在** | ✅ |
| 的/地/得 | 之人**的**心中 | **地** | **的** | ✅ |
| Look-alike char | 一代人的**记**忆 | **纪**忆 | **记**忆 | ✅ |
| Look-alike char | 就**在**叶伏天 | 就**再** | 就**在** | ✅ |
| Anti-piracy junk (×2) | 叶施主 | 叶**‘**施**’**主 | 叶施主 | ✅ |
| Anti-piracy junk | 容颜 | 容**/**颜 | 容颜 | ✅ |
| Half-width punct. | 好漂亮。” | 好漂亮。" | 好漂亮。” | ✅ |
| `**` mask | 显然**认识**来人 | 显然\*\*识 | 显然**认得** | ⚠️ right meaning, different word |
| `**` mask | 一件**事** | 一件\*\* | 一件**小事** | ⚠️ right meaning, extra character |
| Look-alike char | 不**在**了 | 不**再**了 | 不**再**了 | ❌ missed |
| Duplicated char | 点头 | 点**点**头 | 点**点**头 | ❌ missed |

8 of the 12 errors were restored exactly. For 2 `**` masks, the model filled in a word with the right meaning but different wording. 2 errors were missed. No other text was changed.

## Training

QLoRA 4-bit (nf4) with LoRA r=16 / α=32 on all linear layers. Context length 4096, learning rate 1e-4 (cosine), 1 epoch. The training set had 5,000 continuation and 4,000 proofreading samples (about 16M tokens). Training took 6 h 50 min on an RTX 4070 Laptop GPU (8 GB).

The proofreading data was made by adding synthetic noise to clean text: 8 noise types at three densities (light, medium, heavy), plus 10% clean samples. The data-cleaning pipeline is described in [PLAN.md](PLAN.md) (Chinese) and implemented in `scripts/s1~s5`. Training scripts, training configs and datasets are not published.

## Limitations

- Proofreading skill comes mostly from synthetic noise. It works as a typo and formatting cleaner, not as a literary editor.
- For continuation, generate 400–800 tokens at a time and keep `repetition_penalty=1.08` and `no_repeat_ngram_size=8`. Without them, the output tends to repeat whole paragraphs.
- Works only with Qwen3-4B-Instruct-2507, not the thinking variant or other Qwen3 sizes.

## License

Code is released under [GPL-3.0](LICENSE). The LoRA weights were trained on copyrighted web novels and are for personal study and research only, not for commercial use. The base model is under Apache-2.0.
