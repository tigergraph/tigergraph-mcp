"""Data loading crews: draft, edit, and run loading jobs."""

from functools import cached_property
from typing import Any, Dict

from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class DataLoadingCrews:
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
    def _schema_tool(self):
        return self._tools.get("tigergraph__get_graph_schema")

    @cached_property
    def _create_loading_job_tool(self):
        return self._tools.get("tigergraph__create_loading_job")

    @agent
    def draft_loading_agent(self) -> Agent:
        tools = [self._schema_tool] if self._schema_tool else []
        return Agent(
            config=self.agents_config["draft_loading_agent"],
            tools=tools,
            llm=self.llm,
        )

    @agent
    def edit_loading_agent(self) -> Agent:
        return Agent(config=self.agents_config["edit_loading_agent"], llm=self.llm)

    @agent
    def run_loading_agent(self) -> Agent:
        tools = [self._create_loading_job_tool] if self._create_loading_job_tool else []
        return Agent(
            config=self.agents_config["run_loading_agent"],
            tools=tools,
            llm=self.llm,
        )

    @task
    def draft_loading_task(self) -> Task:
        return Task(config=self.tasks_config["draft_loading_task"])

    @task
    def edit_loading_task(self) -> Task:
        return Task(config=self.tasks_config["edit_loading_task"])

    @task
    def run_loading_task(self) -> Task:
        return Task(config=self.tasks_config["run_loading_task"])

    @crew
    def draft_loading_job_crew(self) -> Crew:
        return Crew(
            agents=[self.draft_loading_agent()],
            tasks=[self.draft_loading_task()],
            verbose=self.verbose,
        )

    @crew
    def edit_loading_job_crew(self) -> Crew:
        return Crew(
            agents=[self.edit_loading_agent()],
            tasks=[self.edit_loading_task()],
            verbose=self.verbose,
        )

    @crew
    def run_loading_job_crew(self) -> Crew:
        return Crew(
            agents=[self.run_loading_agent()],
            tasks=[self.run_loading_task()],
            verbose=self.verbose,
        )
