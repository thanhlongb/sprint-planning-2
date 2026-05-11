import logging
import os
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Template
from app.template_schema import load_yaml_template, TemplateValidationError

log = logging.getLogger(__name__)

async def load_templates() -> None:
    """Scan the templates directory, parse YAML files, and load them into DB."""
    # Assuming templates are in src/platform/templates/ relative to this file's grand-parent
    base_dir = Path(__file__).parent.parent
    templates_dir = base_dir / "templates"
    
    if not templates_dir.exists():
        log.warning("Templates directory %s does not exist. Skipping template loading.", templates_dir)
        return
        
    async with SessionLocal() as db:
        for filename in os.listdir(templates_dir):
            if not (filename.endswith(".yaml") or filename.endswith(".yml")):
                continue
                
            filepath = templates_dir / filename
            try:
                parsed_template = load_yaml_template(str(filepath))
            except TemplateValidationError as exc:
                log.error("Failed to load template %s: %s", filename, exc)
                continue
                
            with open(filepath, "r", encoding="utf-8") as f:
                raw_yaml = f.read()

            # Upsert into DB
            result = await db.execute(select(Template).where(Template.id == parsed_template.template_id))
            existing = result.scalar_one_or_none()
            
            # Serialize Pydantic objects to dicts for JSON columns
            phases_data = [p.model_dump() for p in parsed_template.phases]
            
            if existing:
                existing.name = parsed_template.name
                existing.description = parsed_template.description
                existing.raw_yaml = raw_yaml
                existing.phases = phases_data
                existing.inputs = parsed_template.inputs
                existing.outputs = parsed_template.outputs
                log.info("Updated template '%s' from %s", parsed_template.template_id, filename)
            else:
                new_template = Template(
                    id=parsed_template.template_id,
                    name=parsed_template.name,
                    description=parsed_template.description,
                    raw_yaml=raw_yaml,
                    phases=phases_data,
                    inputs=parsed_template.inputs,
                    outputs=parsed_template.outputs,
                )
                db.add(new_template)
                log.info("Inserted template '%s' from %s", parsed_template.template_id, filename)
                
        await db.commit()
