#!/usr/bin/env python3
"""template_demo.py -- Template system demonstration.

Shows JARVIS's template engine: spec templates, prompt templates,
template rendering, custom templates, and parameter validation.

Run:
    python examples/template_demo.py
"""

from __future__ import annotations

import asyncio
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    print("ERROR: `rich` is required.  pip install rich")
    sys.exit(1)

try:
    from jarvis.templates.spec_templates import (
        BUILTIN_SPEC_TEMPLATES,
        SpecTemplate,
        StepTemplate,
        TemplateParameter,
    )
    from jarvis.templates.prompt_templates import PromptLibrary, PromptTemplate
except ImportError as exc:
    print(f"ERROR: Cannot import jarvis modules: {exc}")
    sys.exit(1)

console = Console()


async def main() -> None:
    console.print(Panel("[bold cyan]JARVIS -- Template Demo[/bold cyan]",
                        subtitle="Spec Templates & Prompt Templates"))

    # -------------------------------------------------------------------
    # 1. List built-in spec templates
    # -------------------------------------------------------------------
    console.print("\n[bold]1. Built-in spec templates:[/bold]")
    table = Table(title=f"{len(BUILTIN_SPEC_TEMPLATES)} Spec Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Parameters")
    table.add_column("Steps", justify="right")
    table.add_column("Tags", max_width=30)

    for tmpl in BUILTIN_SPEC_TEMPLATES:
        params = ", ".join(p.name for p in tmpl.parameters)
        table.add_row(
            tmpl.name,
            tmpl.category,
            params,
            str(len(tmpl.steps_template)),
            ", ".join(tmpl.tags[:3]),
        )
    console.print(table)

    # -------------------------------------------------------------------
    # 2. Render an API development template
    # -------------------------------------------------------------------
    console.print("\n[bold]2. Render 'api-development' template:[/bold]")
    api_tmpl = next(t for t in BUILTIN_SPEC_TEMPLATES if t.name == "api-development")

    # Show parameters
    console.print("   Parameters:")
    for p in api_tmpl.list_parameters():
        req = "(required)" if p["required"] else f"(default={p['default']})"
        console.print(f"   - {p['name']}: {p['description']} {req}")

    # Render
    rendered = api_tmpl.render({"name": "UserAuth", "framework": "FastAPI"})
    console.print(f"\n   Intent: {rendered['intent']}")
    console.print(f"   Steps:")
    for step in rendered["steps"]:
        console.print(f"   {step['order']}. {step['name']}: {step['description']}")
    console.print(f"   Constraints:")
    for c in rendered["constraints"]:
        console.print(f"   - {c}")

    # -------------------------------------------------------------------
    # 3. Render a deploy template
    # -------------------------------------------------------------------
    console.print("\n[bold]3. Render 'deploy' template:[/bold]")
    deploy_tmpl = next(t for t in BUILTIN_SPEC_TEMPLATES if t.name == "deploy")
    rendered = deploy_tmpl.render({"service": "payment-api", "environment": "production"})
    console.print(f"   Intent: {rendered['intent']}")
    for step in rendered["steps"]:
        console.print(f"   {step['order']}. {step['name']}")

    # -------------------------------------------------------------------
    # 4. Prompt template library
    # -------------------------------------------------------------------
    console.print("\n[bold]4. Prompt template library:[/bold]")
    library = PromptLibrary()

    console.print(f"   Total templates: {len(library)}")
    console.print(f"   Categories: {library.categories}")

    table = Table(title="Prompt Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Variables", max_width=40)

    for tmpl in library.list_templates():
        table.add_row(
            tmpl.name,
            tmpl.category,
            ", ".join(tmpl.variables[:5]),
        )
    console.print(table)

    # -------------------------------------------------------------------
    # 5. Render a prompt template
    # -------------------------------------------------------------------
    console.print("\n[bold]5. Render prompt templates:[/bold]")

    # Code review
    review_prompt = library.render(
        "code_review_detailed",
        focus_areas="security, performance",
        language="Python",
        context="REST API authentication module",
        security_level="high",
        code="def login(user, pwd): return check(user, pwd)",
    )
    console.print(Panel(review_prompt[:300] + "...", title="Code Review Prompt"))

    # Meeting agenda
    agenda = library.render(
        "meeting_agenda",
        title="Sprint Planning",
        duration="1 hour",
        attendees="Team Alpha",
        purpose="Plan sprint 42",
        action_items="Review backlog, assign tasks",
    )
    console.print(Panel(agenda[:300] + "...", title="Meeting Agenda Prompt"))

    # -------------------------------------------------------------------
    # 6. Search templates
    # -------------------------------------------------------------------
    console.print("\n[bold]6. Search templates:[/bold]")
    results = library.search("security")
    console.print(f"   Search 'security': {len(results)} result(s)")
    for r in results:
        console.print(f"   - {r.name}: {r.description[:60]}")

    results = library.search("code")
    console.print(f"   Search 'code': {len(results)} result(s)")
    for r in results:
        console.print(f"   - {r.name}")

    # -------------------------------------------------------------------
    # 7. Create custom templates
    # -------------------------------------------------------------------
    console.print("\n[bold]7. Custom templates:[/bold]")

    # Custom spec template
    custom_spec = SpecTemplate(
        name="microservice",
        description="Create a new microservice from scratch.",
        category="development",
        intent_template="Create {name} microservice using {language}",
        parameters=[
            TemplateParameter(name="name", description="Service name"),
            TemplateParameter(name="language", description="Programming language",
                              default="Python", choices=["Python", "Go", "Java"]),
        ],
        steps_template=[
            StepTemplate(order=1, name_template="Scaffold {name} project"),
            StepTemplate(order=2, name_template="Implement core logic",
                          depends_on_indices=[0]),
            StepTemplate(order=3, name_template="Add Docker support",
                          depends_on_indices=[1]),
            StepTemplate(order=4, name_template="Write CI/CD pipeline",
                          depends_on_indices=[2]),
        ],
        constraints_template=["Use {language} best practices", "Include health check endpoint"],
        tags=["microservice", "scaffolding"],
    )

    rendered = custom_spec.render({"name": "OrderService", "language": "Go"})
    console.print(f"   Custom spec rendered:")
    console.print(f"   Intent: {rendered['intent']}")
    for step in rendered["steps"]:
        console.print(f"   {step['order']}. {step['name']}")

    # Custom prompt template
    custom_prompt = PromptTemplate(
        name="pr_review",
        description="Review a pull request.",
        category="code",
        template="Review PR #{pr_number}: {title}\n\nChanges:\n{diff}\n\nFocus on: {focus}",
        variables=["pr_number", "title", "diff", "focus"],
    )
    library.add(custom_prompt)

    rendered = library.render("pr_review",
                              pr_number="42",
                              title="Add JWT auth",
                              diff="+def verify_token(token): ...",
                              focus="security")
    console.print(f"\n   Custom prompt rendered:")
    console.print(f"   {rendered[:120]}...")

    # Check missing variables
    missing = custom_prompt.missing_variables(pr_number="42")
    console.print(f"   Missing variables: {missing}")

    console.print("\n[bold green]Demo complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
