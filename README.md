# 网文续写 + 校对 LoRA（Qwen3-4B）

[English](README_EN.md) | 中文

基于 **Qwen3-4B-Instruct-2507** 的 QLoRA 适配器，一个 LoRA 同时完成两项任务：

- **校对**：修正错别字、的地得、标点、防盗插字、拼音替字、`**` 屏蔽等
- **续写**：按上文的文风往下写

## 效果

| 指标 | 结果 |
|---|---|
| 续写 PPL | 27.55 → **20.32**（-26.2%） |
| 校对纠错率 | **74.9%**（轻 70.9% / 中 79.3% / 重 73.5%） |
| 校对字符准确率 | **99.71%**；干净文本误改率 0.0001 |

以上数据来自训练时未见过的书。完整报告见 `work/08_eval/`。

## 快速开始

```bash
# 1. 环境（Python 3.12）
uv venv venv-train --python 3.12
uv pip install --python ./venv-train/bin/python torch --index-url https://download.pytorch.org/whl/cu126  # CPU 用 /whl/cpu
uv pip install --python ./venv-train/bin/python "transformers==5.6.0" "peft==0.18.1" accelerate bitsandbytes modelscope

# 2. 基座 + LoRA 权重
./venv-train/bin/modelscope download --model Qwen/Qwen3-4B-Instruct-2507 --local_dir models/Qwen3-4B-Instruct-2507
curl -L -o work/07_train/std/adapter_model.safetensors \
  https://github.com/ArchitektSpeer/novel-lora-qwen3-4b/releases/download/v1.0/adapter_model.safetensors

# 3. 校对
./venv-train/bin/python scripts/demo_proofread.py --input dirty.txt --output fixed.txt
./venv-train/bin/python scripts/demo_proofread.py --web          # 网页界面，需先 pip install gradio

# 4. 续写
./venv-train/bin/python scripts/t6_infer_demo.py --adapter work/07_train/std \
  --mode continue --prompt-file prefix.txt --max-new 800
```

- 有 GPU 时以 4bit 加载，显存约 4GB。没有 GPU 时自动改用 CPU bf16，需要约 10GB 内存。
- 长文本会自动切成 1200 字以内的段落，逐段校对。
- 不要安装 `kernels` 包，它与 transformers 5.6 不兼容。

## 校对示例

一段 718 字的网文，注入了 12 处错误。用 i5-8250U 纯 CPU 跑，耗时约 7 分钟。

| 类型 | 原文 | 脏文本 | 模型输出 | |
|---|---|---|---|---|
| 形近字 | 会**在**东荒 | 会**再** | 会**在** | ✅ |
| 的地得 | 之人**的**心中 | **地** | **的** | ✅ |
| 形近字 | 一代人的**记**忆 | **纪**忆 | **记**忆 | ✅ |
| 形近字 | 就**在**叶伏天 | 就**再** | 就**在** | ✅ |
| 防盗插字（2 处） | 叶施主 | 叶**‘**施**’**主 | 叶施主 | ✅ |
| 防盗插字 | 容颜 | 容**/**颜 | 容颜 | ✅ |
| 半角标点 | 好漂亮。” | 好漂亮。" | 好漂亮。” | ✅ |
| `**` 屏蔽 | 显然**认识**来人 | 显然\*\*识 | 显然**认得** | ⚠️ 意思对，用字不同 |
| `**` 屏蔽 | 一件**事** | 一件\*\* | 一件**小事** | ⚠️ 意思对，多了一个字 |
| 形近字 | 不**在**了 | 不**再**了 | 不**再**了 | ❌ 漏改 |
| 叠字 | 点头 | 点**点**头 | 点**点**头 | ❌ 漏改 |

12 处中有 8 处完全还原，2 处 `**` 屏蔽补出的词意思正确，2 处漏改。其余正文没有被误改。

## 训练配置

QLoRA 4bit（nf4），LoRA r=16 / α=32，作用于全部线性层。上下文长度 4096，学习率 1e-4（cosine），1 epoch。训练数据为 5,000 条续写和 4,000 条校对样本（约 16M token），在 RTX 4070 Laptop（8GB）上跑了 6 小时 50 分。

校对数据是往干净正文里合成噪声得到的：共 8 类噪声，按轻/中/重三档密度生成，另有 10% 不加噪声的干净样本。数据清洗流程见 [PLAN.md](PLAN.md) 和 `scripts/s1~s5`。训练脚本、训练配置和数据集不公开。

## 局限

- 校对能力主要来自合成噪声，适合做错别字和格式清洗，不能当文学编辑用。
- 续写建议每次生成 400~800 token，并保留 `repetition_penalty=1.08` 和 `no_repeat_ngram_size=8`，否则容易整段复读。
- 只适用于 Qwen3-4B-Instruct-2507，不能用于 thinking 版或其他尺寸的模型。

## 许可

代码以 [GPL-3.0](LICENSE) 发布。LoRA 权重由有版权的网络小说训练而来，仅供个人学习与研究，不得用于商业用途。基座模型遵循 Apache-2.0。
