"""Planner crew: onboarding detection and task planning (no tools, LLM only)."""

from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class PlannerCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, verbose: int = 0, llm: str = "openai/gpt-4.1-mini-2025-04-14"):
        self.verbose = verbose
        self.llm = llm

    @agent
    def onboarding_detector_agent(self) -> Agent:
        return Agent(config=self.agents_config["onboarding_detector_agent"], llm=self.llm)

    @agent
    def planner_agent(self) -> Agent:
        return Agent(config=self.agents_config["planner_agent"], llm=self.llm)

    @task
    def onboarding_detector_task(self) -> Task:
        return Task(config=self.tasks_config["onboarding_detector_task"])

    @task
    def planning_task(self) -> Task:
        return Task(config=self.tasks_config["planning_task"])

    @crew
    def onboarding_detector_crew(self) -> Crew:
        return Crew(
            agents=[self.onboarding_detector_agent()],
            tasks=[self.onboarding_detector_task()],
            verbose=self.verbose,
        )

    @crew
    def planning_crew(self) -> Crew:
        return Crew(
            agents=[self.planner_agent()],
            tasks=[self.planning_task()],
            verbose=self.verbose,
        )
