from backend.models import QueryIntent, Scope, SearchMode
from backend.retrieval.query_planning import QueryParser, QueryPlanner


class TestQueryParser:
    def test_parse_inline_mode_and_tag(self):
        parser = QueryParser()

        parsed = parser.parse(
            raw_text="/diary 最後にビールを飲んだのはいつ? #飲み会",
            ui_search_mode=SearchMode.AUTO,
            ui_scope=None,
        )

        assert parsed.search_mode == SearchMode.DIARY
        assert parsed.query_text == "最後にビールを飲んだのはいつ?"
        assert parsed.scope is not None
        assert parsed.scope.tags == ["飲み会"]

    def test_parse_command_scope_overrides_ui_folder_and_merges_tags(self):
        parser = QueryParser()

        parsed = parser.parse(
            raw_text="/general project update #backend @projects",
            ui_search_mode=SearchMode.AUTO,
            ui_scope=Scope(folder="old", tags=["work"]),
        )

        assert parsed.search_mode == SearchMode.GENERAL
        assert parsed.scope is not None
        assert parsed.scope.folder == "projects"
        assert parsed.scope.tags == ["work", "backend"]


class TestQueryPlanner:
    def test_build_plan_prefers_diary_intent_for_diary_command(self):
        parser = QueryParser()
        planner = QueryPlanner()

        parsed = parser.parse(
            raw_text="/diary 昨日何を食べた?",
            ui_search_mode=SearchMode.AUTO,
            ui_scope=None,
        )
        plan = planner.build_plan(parsed, history=[])

        assert plan.search_mode == SearchMode.DIARY
        assert plan.is_diary_intent is True
        assert plan.is_temporal is True
        assert plan.primary_intent == QueryIntent.TEMPORAL

    def test_build_plan_classifies_general_context_query(self):
        parser = QueryParser()
        planner = QueryPlanner()

        parsed = parser.parse(
            raw_text="/general API設計について教えて",
            ui_search_mode=SearchMode.AUTO,
            ui_scope=None,
        )
        plan = planner.build_plan(parsed, history=[])

        assert plan.search_mode == SearchMode.GENERAL
        assert plan.is_context_query is True
        assert plan.primary_intent == QueryIntent.CONTEXT
