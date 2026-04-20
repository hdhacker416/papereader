import json

from sqlalchemy.orm import Session

from app_constants import DEFAULT_USER_ID
import models


DEFAULT_RESEARCH_TEMPLATE = [
    "请你使用中文总结一下这篇文章的内容，并且举一个例子加以说明。"
]


def normalize_prompt_list(prompts: list[str] | None) -> list[str]:
    if not prompts:
        return []
    normalized = [item.strip() for item in prompts if item and item.strip()]
    return normalized


def parse_template_prompts(content: str) -> list[str]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return normalize_prompt_list([str(item) for item in parsed])
    except json.JSONDecodeError:
        pass
    return normalize_prompt_list([content])


def serialize_prompt_list(prompts: list[str] | None) -> str | None:
    normalized = normalize_prompt_list(prompts)
    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=False)


def ensure_default_template(db: Session):
    template = db.query(models.Template).filter(
        models.Template.user_id == DEFAULT_USER_ID,
        models.Template.is_default == True,
    ).first()
    if template:
        return template

    template = db.query(models.Template).filter(
        models.Template.user_id == DEFAULT_USER_ID
    ).first()
    if template:
        template.is_default = True
        db.commit()
        db.refresh(template)
        return template

    template = models.Template(
        user_id=DEFAULT_USER_ID,
        name="Default Paper Summary",
        content=json.dumps(DEFAULT_RESEARCH_TEMPLATE),
        is_default=True,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template
