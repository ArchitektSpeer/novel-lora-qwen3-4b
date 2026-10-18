# 小说续写 + 校对 LoRA（Qwen3-4B-Instruct-2507）

基于清洗后的中文网络小说语料，用 QLoRA 在 **Qwen3-4B-Instruct-2507** 上训练的单 LoRA 双任务模型：

- **自动补全**：给一段上文，按原文文风续写下文
- **小说校对**：给带错别字/标点错误/防盗插字的脏文本，输出修正后的干净文本

训练使用 LLaMA-Factory 0.9.5 + transformers 5.6.0，在 8GB 显存（RTX 4070 Laptop）上完成。本仓库提供 LoRA 权重、推理/校对 demo、评估脚本与数据清洗线；训练脚本、训练配置与训练集不公开。

## 训练结果（std 档，2026-10-18）

| 指标 | 数值 |
|---|---|
| 训练步数 / 时长 | 563 步 / 6 小时 50 分（1 epoch） |
| train_loss | 1.313 |
| 续写 PPL（teacher-forced，150 chunk） | base **27.55** → LoRA **20.32**，**-26.2%** |
| 分题材 PPL | 玄幻修真 -27.5%、末世都市 -26.8%、游戏玄幻 -24.7% |
| 校对纠错率（120 条分层） | **74.9%**（light 70.9% / medium 79.3% / heavy 73.5%） |
| 校对字符准确率 | **99.71%**，阴性样本误改率 **0.0001** |
| 干净样本完全一致率 | 90% |

完整报告见 `work/08_eval/ppl_report_std.md`、`work/08_eval/proofread_report_std.md`。

注：`train_loss 1.313` 偏低——训练中途从 checkpoint-150 续跑，HF 只累加续跑后的 loss 却除以全部步数；`trainer_log.jsonl` 里各段 loss 实际在 1.6~2.0。

## 模型规格

| 项 | 值 |
|---|---|
| 基座 | `Qwen/Qwen3-4B-Instruct-2507`（不随包提供，需自行下载） |
| 微调方式 | QLoRA 4bit（nf4 + double quant）+ LoRA |
| LoRA 参数 | r=16，alpha=32，dropout=0.05，`lora_target: all`，可训练参数 33,030,144 |
| 训练长度 | cutoff_len 4096，batch 1 × grad_accum 16，lr 1e-4 cosine，warmup 3% |
| 混合精度 | bf16 + 梯度检查点 + liger kernel + paged_adamw_8bit |
| Adapter 大小 | 127 MB（[Release v1.0](https://github.com/ArchitektSpeer/novel-lora-qwen3-4b/releases/tag/v1.0) 附件） |

## 仓库内容

```
README.md                     本文件
PLAN.md                       数据清洗/标注计划与五轮 QC 记录
scripts/demo_proofread.py     网文校对 demo（命令行 / Gradio 网页）
scripts/t_common.py           模型加载与生成（GPU 4bit / CPU bf16）
scripts/t4~t6_*.py            续写 PPL 评估、校对评估、续写+校对演示
scripts/s1~s5_*.py 等         数据清洗线、规则与回归用例
work/07_train/std/            adapter 配置、tokenizer、训练日志、loss 曲线（权重见 Release）
work/08_eval/                 PPL/校对报告、推理演示输出
work/reports/                 数据清洗阶段的 QC 日志与统计
work/05_dataset/stats.md      最终数据集统计
```

不公开：训练集与评估集（所有 `*.jsonl`）、训练脚本与 LLaMA-Factory 配置、原始语料、基座权重。

## 快速开始

### 1. 准备环境

```bash
uv venv venv-train --python 3.12
# 有 NVIDIA GPU：
uv pip install --python ./venv-train/bin/python torch --index-url https://download.pytorch.org/whl/cu126
uv pip install --python ./venv-train/bin/python bitsandbytes
# 只有 CPU：
uv pip install --python ./venv-train/bin/python torch --index-url https://download.pytorch.org/whl/cpu

uv pip install --python ./venv-train/bin/python "transformers==5.6.0" "peft==0.18.1" accelerate modelscope
```

不要安装 `kernels` 包：它与 transformers 5.6 不兼容，会导致 `import transformers` 直接报错。

### 2. 下载基座

```bash
export PATH="$HOME/.local/bin:$PATH"
modelscope download --model Qwen/Qwen3-4B-Instruct-2507 \
  --local_dir "models/Qwen3-4B-Instruct-2507"
```

### 2.1 下载 LoRA 权重

```bash
curl -L -o work/07_train/std/adapter_model.safetensors \
  https://github.com/ArchitektSpeer/novel-lora-qwen3-4b/releases/download/v1.0/adapter_model.safetensors
```

### 3. 推理演示

```bash
cd novel-lora-qwen3-4b-std-20261018   # 项目根目录
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# 一次续写 + 一次校对
./venv-train/bin/python scripts/t6_infer_demo.py --adapter work/07_train/std

# 用自己的上文续写
./venv-train/bin/python scripts/t6_infer_demo.py --adapter work/07_train/std \
  --mode continue --prompt-file my_prefix.txt --max-new 800
```

不带 `--prompt-file` / `--proofread-file` 时，t6 会从评估集里随机抽样，而评估集不随仓库提供。

### 3.1 网文校对 demo

`scripts/demo_proofread.py` 把任意长度的文本按段落切成训练时的长度（≤1200 字）逐段贪心解码，拼回全文，并列出每一处改动。某段输出长度偏离输入超过 15%（模型跑偏/截断）时，该段保留原文。

```bash
# 命令行：文件进、文件出，改动清单打到 stderr
./venv-train/bin/python scripts/demo_proofread.py --input dirty.txt --output fixed.txt
cat dirty.txt | ./venv-train/bin/python scripts/demo_proofread.py > fixed.txt

# 网页：左右对照 + 红删绿增的改动高亮
uv pip install --python ./venv-train/bin/python gradio
./venv-train/bin/python scripts/demo_proofread.py --web --port 7860   # 打开 http://127.0.0.1:7860
```

默认 `--model models/Qwen3-4B-Instruct-2507 --adapter work/07_train/std`。有 CUDA 时以 4bit 加载（显存约 4GB 以上）；没有 GPU 时自动改为 CPU bf16，并把 adapter 合并进基座（内存约 10GB，速度见 §3.2）。

### 3.2 校对效果示例

样本取自 `test_holdout`（按书隔离，训练时从未见过）中的一条中密度样本，共 718 字，注入了 12 处错误。用 `scripts/demo_proofread.py` 在纯 CPU 上跑（i5-8250U 笔记本 8 线程，bf16，无 GPU），耗时约 7 分钟。

| # | 错误类型 | 原文 | 脏文本 | 模型输出 | 结果 |
|---|---|---|---|---|---|
| 1 | 形近字 | 草堂虽然不**在**了 | 不**再**了 | 不**再**了 | ❌ 漏改（「不再了」本身也通顺） |
| 2 | 形近字 | 永远都会**在**东荒之人 | 会**再** | 会**在** | ✅ |
| 3 | 的地得 | 东荒之人**的**心中 | 之人**地**心中 | 之人**的**心中 | ✅ |
| 4 | 形近字 | 一代人的**记**忆 | **纪**忆 | **记**忆 | ✅ |
| 5 | 形近字 | 就**在**叶伏天准备 | 就**再** | 就**在** | ✅ |
| 6 | `**` 屏蔽 | 显然**认识**来人 | 显然**\*\*识**来人 | 显然**认得**来人 | ⚠️ 补全合理，用字不同 |
| 7 | 防盗插字 | 容颜纯美 | 容**/**颜 | 容颜 | ✅ |
| 8 | 半角标点 | 好漂亮。**”** | 好漂亮。**"** | 好漂亮。**”** | ✅ |
| 9 | 叠字 | 微笑着点头 | 点**点**头 | 点**点**头 | ❌ 漏改（「点点头」本身也通顺） |
| 10–11 | 防盗插字 | 叶施主 | 叶**‘**施**’**主 | 叶施主 | ✅✅ |
| 12 | `**` 屏蔽 | 一件**事** | 一件**\*\*** | 一件**小事** | ⚠️ 补全合理，多了「小」字 |

**结果**：12 处错误里 8 处完全还原，2 处 `**` 屏蔽按上下文补出了意思正确、但用字不同的词，2 处漏改（漏改后的句子仍然通顺）。其余正文没有被误改。字符准确率从 98.89% 升到 99.72%。

<details>
<summary>完整文本：脏文本 / 模型输出 / 原文</summary>

**脏文本**

```text
叶伏天在书院停留了数日，陪伴着老师师娘他们，这次离开又不知何时能够回来，不过见到老师他们在这里过的开心，叶伏天便也放心了许多。
叶无尘和柳沉鱼一起回了苍叶国一趟，之后返回书山，准备带着柳沉鱼一起前往至圣道宫。
无尘拜入剑魔门下，是属于亲传，可以携带家眷，自然不打算继续将柳沉鱼一人留在此地。
这些事情处理完毕，书山之上，一行人站在一起，便准备启程离开了。
修行路漫漫，他们并没有太多的时间可以浪费耽搁，正如大师兄所想的那样，叶伏天也想要看看前方的风景。
书山许多人都来送行，各山山主也都到了，还有诸多书院弟子，草堂虽然不再了，草堂弟子，却永远都会再东荒之人地心中，那是一代人的纪忆。
就再叶伏天准备启程之时，远处却见两道身影乘云而来，直奔叶伏天这边，书院弟子也未阻拦，显然**识来人。
这两人颇为奇怪，其中一人乃是一位高僧，宝相庄严，另一人则是一位绝色女子，拥有惊世之颜，她身穿素衣，浑身纤尘不染，容/颜纯美无暇，如真正的无暇碧玉，不曾染世间尘埃，而且她的气质极为不凡，身上像是有着看不见的奇妙光泽。
这女子眼眸带着浅浅的笑容，目光望向叶伏天等人。
“好漂亮。"叶伏天身边的龙灵儿嘀咕了一声，这到来的女子容颜倾世，而她身上那股不染尘埃的纯美气质，美到不似人间之人，已是能够和解语姐姐相媲美了。
“大师。”刀圣见到高僧前来不由得微笑着点点头，原来这僧人乃是千秋寺的住持。
“刀圣施主。”大师双手合十行礼，随后目光落在叶伏天身上，道：“听闻叶‘施’主从荒州回来，因此特意来此一趟，拜托叶施主一件**。”
“大师请讲。”叶伏天目光从女子身上移开。
当年东华宗被灭门，华青青遭遇人间惨剧，后入千秋寺修行，如今看到她气质容颜更甚往昔，想必千秋寺对她非常照顾。
```

**模型输出**

```text
叶伏天在书院停留了数日，陪伴着老师师娘他们，这次离开又不知何时能够回来，不过见到老师他们在这里过的开心，叶伏天便也放心了许多。
叶无尘和柳沉鱼一起回了苍叶国一趟，之后返回书山，准备带着柳沉鱼一起前往至圣道宫。
无尘拜入剑魔门下，是属于亲传，可以携带家眷，自然不打算继续将柳沉鱼一人留在此地。
这些事情处理完毕，书山之上，一行人站在一起，便准备启程离开了。
修行路漫漫，他们并没有太多的时间可以浪费耽搁，正如大师兄所想的那样，叶伏天也想要看看前方的风景。
书山许多人都来送行，各山山主也都到了，还有诸多书院弟子，草堂虽然不再了，草堂弟子，却永远都会在东荒之人的心中，那是一代人的记忆。
就在叶伏天准备启程之时，远处却见两道身影乘云而来，直奔叶伏天这边，书院弟子也未阻拦，显然认得来人。
这两人颇为奇怪，其中一人乃是一位高僧，宝相庄严，另一人则是一位绝色女子，拥有惊世之颜，她身穿素衣，浑身纤尘不染，容颜纯美无暇，如真正的无暇碧玉，不曾染世间尘埃，而且她的气质极为不凡，身上像是有着看不见的奇妙光泽。
这女子眼眸带着浅浅的笑容，目光望向叶伏天等人。
“好漂亮。”叶伏天身边的龙灵儿嘀咕了一声，这到来的女子容颜倾世，而她身上那股不染尘埃的纯美气质，美到不似人间之人，已是能够和解语姐姐相媲美了。
“大师。”刀圣见到高僧前来不由得微笑着点点头，原来这僧人乃是千秋寺的住持。
“刀圣施主。”大师双手合十行礼，随后目光落在叶伏天身上，道：“听闻叶施主从荒州回来，因此特意来此一趟，拜托叶施主一件小事。”
“大师请讲。”叶伏天目光从女子身上移开。
当年东华宗被灭门，华青青遭遇人间惨剧，后入千秋寺修行，如今看到她气质容颜更甚往昔，想必千秋寺对她非常照顾。
```

**原文**

```text
叶伏天在书院停留了数日，陪伴着老师师娘他们，这次离开又不知何时能够回来，不过见到老师他们在这里过的开心，叶伏天便也放心了许多。
叶无尘和柳沉鱼一起回了苍叶国一趟，之后返回书山，准备带着柳沉鱼一起前往至圣道宫。
无尘拜入剑魔门下，是属于亲传，可以携带家眷，自然不打算继续将柳沉鱼一人留在此地。
这些事情处理完毕，书山之上，一行人站在一起，便准备启程离开了。
修行路漫漫，他们并没有太多的时间可以浪费耽搁，正如大师兄所想的那样，叶伏天也想要看看前方的风景。
书山许多人都来送行，各山山主也都到了，还有诸多书院弟子，草堂虽然不在了，草堂弟子，却永远都会在东荒之人的心中，那是一代人的记忆。
就在叶伏天准备启程之时，远处却见两道身影乘云而来，直奔叶伏天这边，书院弟子也未阻拦，显然认识来人。
这两人颇为奇怪，其中一人乃是一位高僧，宝相庄严，另一人则是一位绝色女子，拥有惊世之颜，她身穿素衣，浑身纤尘不染，容颜纯美无暇，如真正的无暇碧玉，不曾染世间尘埃，而且她的气质极为不凡，身上像是有着看不见的奇妙光泽。
这女子眼眸带着浅浅的笑容，目光望向叶伏天等人。
“好漂亮。”叶伏天身边的龙灵儿嘀咕了一声，这到来的女子容颜倾世，而她身上那股不染尘埃的纯美气质，美到不似人间之人，已是能够和解语姐姐相媲美了。
“大师。”刀圣见到高僧前来不由得微笑着点头，原来这僧人乃是千秋寺的住持。
“刀圣施主。”大师双手合十行礼，随后目光落在叶伏天身上，道：“听闻叶施主从荒州回来，因此特意来此一趟，拜托叶施主一件事。”
“大师请讲。”叶伏天目光从女子身上移开。
当年东华宗被灭门，华青青遭遇人间惨剧，后入千秋寺修行，如今看到她气质容颜更甚往昔，想必千秋寺对她非常照顾。
```

</details>

续写采样默认开启 `repetition_penalty=1.08` + `no_repeat_ngram_size=8`（在 `scripts/t_common.py` 中）。**去掉这两个参数会在一段之后出现整段复读**。

### 4. 评估

```bash
./venv-train/bin/python scripts/t4_eval_ppl.py --adapter work/07_train/std
./venv-train/bin/python scripts/t5_eval_proofread.py --adapter work/07_train/std --limit 120
```

评估脚本需要 `work/05_dataset/valid.jsonl` 与 `work/06_sft/proofread/test_holdout.jsonl`，它们不随仓库提供；可以按同样格式准备自己的评估集。

## 数据与训练细节

- **CPT → SFT**：清洗后的 4.16 亿字 chunk 按段落边界切成「上文 / 下文」，85% 标准切分、5% 书头开局、10% 裸文本；30% 携带题材元信息。
- **校对数据**：真实正文注入 8 类噪声（形近字、标点、防盗插字、漏/叠字、的地得、`**` 屏蔽、拼音、空格），密度轻/中/重 3:5:2，另含 10% 阴性（干净）样本抑制过度纠正；混淆表解析自 `scripts/cipher_fix.txt` 与内置表。holdout 取自 `valid.jsonl`，书籍级隔离。
- **std 档**：5,000 条续写 + 4,000 条校对（约 16.2M token），1 epoch。

## 已知限制

- 校对能力主要来自**合成噪声**，对真实世界里作者写错的语义级病句、错词替换泛化有限；建议把它当作「格式/错别字清洗器」，不要当作文学编辑。
- 上下文上限 4096 token；续写建议一次生成 400~800 token，过长仍可能走向重复或灌水。
- GPU 推理用 bitsandbytes 4bit；CPU 推理走 bf16 全精度加载，约需 10GB 内存，速度见 §3.2。
- adapter 只适用于 Qwen3-4B-Instruct-2507，不要挂到 thinking 版或其它尺寸的 Qwen3 上。

## 许可证

代码与文档以 [GPL-3.0](LICENSE) 发布。LoRA 权重派生自有版权的网络小说语料，仅供个人学习与研究，不得用于商业用途；基座模型遵循其自身许可（Apache-2.0）。

## 合规声明

训练语料为**有版权的网络小说**，本仓库不分发任何原始语料、清洗数据或训练集：

- LoRA 权重仅限个人学习/研究，不要用于商业用途
- 引用原文片段时请遵守原作者的版权要求

详见 `PLAN.md` §9。
