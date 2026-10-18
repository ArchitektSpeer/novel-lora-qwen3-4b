#!/usr/bin/env python3
"""t4/t5/t6 共用的模型加载与推理helper。"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def load(path, adapter=None):
    tokenizer = AutoTokenizer.from_pretrained(path)
    if not torch.cuda.is_available():
        # 无 GPU：bf16 不量化（约 8GB 内存），adapter 合并进基座省掉 LoRA 旁路开销
        model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16, low_cpu_mem_usage=True)
        if adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
        model.eval()
        return tokenizer, model
    model = AutoModelForCausalLM.from_pretrained(
        path,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        ),
        device_map="cuda:0",
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
    )
    if adapter:
        from peft import PeftModel
        # 4bit 基座上不做 merge_and_unload，直接挂 adapter 推理
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tokenizer, model


def unload(model):
    del model
    torch.cuda.empty_cache()


def render(tokenizer, instruction, inp):
    messages = []
    if instruction:
        messages.append({"role": "user", "content": instruction + "\n" + inp})
    else:
        messages.append({"role": "user", "content": inp})
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def generate(tokenizer, model, prompt, max_new_tokens=1200, temperature=0.7, top_p=0.9,
             repetition_penalty=1.0, no_repeat_ngram_size=0):
    enc = tokenizer([prompt], return_tensors="pt").to(model.device)
    kwargs = dict(
        max_new_tokens=max_new_tokens,
        do_sample=temperature > 0,
        temperature=temperature,
        top_p=top_p,
        pad_token_id=tokenizer.eos_token_id,
        repetition_penalty=repetition_penalty,
    )
    if no_repeat_ngram_size:
        kwargs["no_repeat_ngram_size"] = no_repeat_ngram_size
    with torch.no_grad():
        out = model.generate(**enc, **kwargs)
    text = tokenizer.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)
    return text.strip()
