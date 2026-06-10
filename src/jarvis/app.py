from __future__ import annotations

import logging
from pathlib import Path

from jarvis.agents.orchestrator import Orchestrator
from jarvis.agents.registry import AgentRegistry
from jarvis.agents.specialists.calendar_agent import CalendarAgent
from jarvis.agents.specialists.code_agent import CodeAgent
from jarvis.agents.specialists.general_agent import GeneralAgent
from jarvis.agents.specialists.comms_agent import CommsAgent
from jarvis.agents.specialists.data_agent import DataAgent
from jarvis.agents.specialists.devops_agent import DevOpsAgent
from jarvis.agents.specialists.knowledge_agent import KnowledgeAgent
from jarvis.agents.specialists.ops_agent import OpsAgent
from jarvis.agents.specialists.research_agent import ResearchAgent
from jarvis.agents.specialists.security_agent import SecurityAgent
from jarvis.agents.specialists.writing_agent import WritingAgent
from jarvis.engine.executor import SpecExecutor
from jarvis.engine.spec_engine import SpecEngine
from jarvis.engine.spec_registry import SpecRegistry
from jarvis.hooks.engine import HookEngine
from jarvis.knowledge.graph import KnowledgeGraph
from jarvis.llm.registry import LLMRegistry
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver
from jarvis.skills.eval import SkillEvaluator
from jarvis.skills.failure_analyzer import FailureAnalyzer
from jarvis.curator.engine import Curator
from jarvis.memory.manager import MemoryManager
from jarvis.session.manager import SessionManager
from jarvis.observability.tracer import tracer

logger = logging.getLogger(__name__)

SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"


class JarvisApp:
    """Top-level application that wires all components together.

    Connects LLM providers, tool registry, agent system, streaming spec engine,
    knowledge graph, and hooks into a unified personal AI assistant.
    """

    def __init__(self, specs_dir: str | Path | None = None) -> None:
        self.llm_registry = LLMRegistry()
        self.registry = AgentRegistry()
        self.orchestrator = Orchestrator(self.registry)
        self.spec_engine = SpecEngine(llm_registry=self.llm_registry)
        self.executor = SpecExecutor(self.spec_engine, self.orchestrator)
        self.spec_registry = SpecRegistry(specs_dir or SPECS_DIR if SPECS_DIR.exists() else None)
        self.hook_engine = HookEngine()
        self.knowledge_graph = KnowledgeGraph()
        self._tool_registry = None

        self.skill_registry = SkillRegistry()
        self.skill_evolver = SkillEvolver(self.skill_registry, self.llm_registry)
        self.skill_evaluator = SkillEvaluator(self.llm_registry)
        self.failure_analyzer = FailureAnalyzer(self.llm_registry)
        self.curator = Curator(self.llm_registry)
        self.memory_manager = MemoryManager()
        self.session_manager = SessionManager()

    def _init_tools(self):
        try:
            import jarvis.tools.builtin  # noqa: F401 — registers tools
            from jarvis.tools import tool_registry
            self._tool_registry = tool_registry
            logger.info("Tool registry: %d tools available", len(tool_registry.list_tools()))
        except Exception as e:
            logger.warning("Tool system init failed: %s", e)

    async def initialize(self) -> None:
        """Register all built-in agents and initialize the system."""
        self._init_tools()

        agents = [
            GeneralAgent(),
            CodeAgent(),
            CalendarAgent(),
            KnowledgeAgent(),
            CommsAgent(),
            OpsAgent(),
            DataAgent(),
            SecurityAgent(),
            DevOpsAgent(),
            WritingAgent(),
            ResearchAgent(),
        ]
        for agent in agents:
            agent.set_llm_registry(self.llm_registry)
            if self._tool_registry:
                agent.set_tool_registry(self._tool_registry)
            await self.registry.register(agent)

        self.orchestrator = Orchestrator(self.registry)
        self.executor = SpecExecutor(self.spec_engine, self.orchestrator)

        # Wire spec engine replanner with LLM
        from jarvis.engine.replanner import Replanner
        self.spec_engine._replanner = Replanner(llm_registry=self.llm_registry)

        skills_loaded = self.skill_registry.load_directory()

        logger.info(
            "JARVIS initialized: %d agents, %d tools, %d specs, %d skills",
            len(self.registry),
            len(self._tool_registry.list_tools()) if self._tool_registry else 0,
            len(self.spec_registry.list_specs()),
            skills_loaded,
        )

    async def chat(self, message: str) -> str:
        """Simple chat interface: route a message to the best agent."""
        result = await self.orchestrator.handle(message)
        return result.output if result.success else f"Error: {result.error}"

    async def run_spec(self, intent: str) -> dict:
        """Create and execute a Streaming Spec end-to-end."""
        spec = await self.spec_engine.create(intent)
        result = await self.executor.execute_spec(spec.id)
        if result:
            return result.model_dump(mode="json")
        return {"error": "Spec execution failed"}

    async def record_skill_execution(self, skill_name: str, execution) -> None:
        """Record a skill execution and trigger reflection + evolution if needed."""
        from jarvis.skills.base import SkillExecution
        skill = self.skill_registry.get(skill_name)
        if not skill:
            return

        skill.record_execution(execution)

        if not execution.success:
            analysis = await self.failure_analyzer.analyze(execution, skill)
            summary = self.failure_analyzer.aggregate(skill_name)
            if self.failure_analyzer.should_trigger_improvement(summary):
                await self._evolve_skill(skill)

    async def _evolve_skill(self, skill) -> None:
        """Run the full evolution pipeline: improve → eval → curator review → promote/rollback."""
        improved = await self.skill_evolver.improve_skill(skill)
        if not improved:
            return

        suite = self.skill_evaluator.get_suite(skill.metadata.name)
        if suite and suite.cases:
            passed = await self.skill_evaluator.regression_test(skill, improved, suite)
            if not passed:
                logger.warning("Skill %s evolution failed regression test, rolling back", skill.metadata.name)
                self.skill_registry.deprecate(improved.metadata.name)
                return

        review = await self.curator.review_skill(improved)
        if review.verdict.value in ("approved", "needs_revision"):
            from jarvis.skills.base import SkillStatus
            improved.status = SkillStatus.ACTIVE
            self.skill_registry.register(improved)
            logger.info("Skill %s evolved to %s", skill.metadata.name, improved.metadata.version)
        else:
            logger.warning("Skill %s evolution rejected by curator: %s", skill.metadata.name, review.verdict)

    async def shutdown(self) -> None:
        self.skill_registry.save_all()
        await self.registry.shutdown_all()
        logger.info("JARVIS shutdown complete")
