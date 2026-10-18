# 续写 PPL 评估（valid.jsonl，teacher-forced，未计 loss mask）

## base：PPL = 27.552（150 chunk）

| 题材 | PPL |
|---|---|
| 玄幻、修真 | 25.768 |
| 末世、都市 | 26.510 |
| 游戏、玄幻 | 30.346 |

## base+LoRA：PPL = 20.321（150 chunk）

| 题材 | PPL |
|---|---|
| 玄幻、修真 | 18.696 |
| 末世、都市 | 19.412 |
| 游戏、玄幻 | 22.863 |

**LoRA 相对 base 的 PPL 下降：26.2%**
