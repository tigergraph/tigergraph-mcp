"""Schema creation crews: draft, edit, and create graph schemas."""

from functools import cached_property
from typing import Any, Dict

from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class SchemaCreationCrews:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(
        self,
        tools: Dict[str, Any],
        verbose: int = 0,
        llm: str = "openai/gpt-4.1-mini-2025-04-14",
    ):
        self._tools = tools
        self.verbose = verbose
        self.llm = llm

    @cached_property
    def _create_graph_tool(self):
        return self._tools.get("tigergraph__create_graph")

    @agent
    def draft_schema_agent(self) -> Agent:
        return Agent(config=self.agents_config["draft_schema_agent"], llm=self.llm)

    @agent
    def edit_schema_agent(self) -> Agent:
        return Agent(config=self.agents_config["edit_schema_agent"], llm=self.llm)

    @agent
    def create_schema_agent(self) -> Agent:
        tools = [self._create_graph_tool] if self._create_graph_tool else []
        return Agent(
            config=self.agents_config["create_schema_agent"],
            tools=tools,
            llm=self.llm,
        )

    @task
    def draft_schema_task(self) -> Task:
        return Task(config=self.tasks_config["draft_schema_task"])

    @task
    def edit_schema_task(self) -> Task:
        return Task(config=self.tasks_config["edit_schema_task"])

    @task
    def create_schema_task(self) -> Task:
        return Task(config=self.tasks_config["create_schema_task"])

    @crew
    def draft_schema_crew(self) -> Crew:
        return Crew(
            agents=[self.draft_schema_agent()],
            tasks=[self.draft_schema_task()],
            verbose=self.verbose,
        )

    @crew
    def edit_schema_crew(self) -> Crew:
        return Crew(
            agents=[self.edit_schema_agent()],
            tasks=[self.edit_schema_task()],
            verbose=self.verbose,
        )

    @crew
    def create_schema_crew(self) -> Crew:
        return Crew(
            agents=[self.create_schema_agent()],
            tasks=[self.create_schema_task()],
            verbose=self.verbose,
        )
