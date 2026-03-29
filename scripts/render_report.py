import json
import sys
from pathlib import Path

from jinja2 import Template
from weasyprint import HTML


def main():
    project_root = Path(__file__).resolve().parent.parent
    template_path = project_root / "templates" / "executive-summary.html"
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else project_root / "output" / "report_data.json"
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else project_root / "output" / "executive-summary.pdf"

    with open(template_path) as f:
        template = Template(f.read())

    with open(data_path) as f:
        data = json.load(f)

    rendered = template.render(**data)

    html_output = output_path.with_suffix(".html")
    html_output.write_text(rendered)

    HTML(string=rendered, base_url=str(template_path.parent)).write_pdf(str(output_path))

    print(f"PDF: {output_path}")
    print(f"HTML: {html_output}")


if __name__ == "__main__":
    main()
