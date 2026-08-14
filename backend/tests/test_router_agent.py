"""Unit tests for RAG routing, crop context extraction, agronomy prompt persona,
and chemical safety reflection checks.
"""


from app.models.document import RetrievedChunk, VisionPrediction
from app.services.prompt_builder import (
    AGRONOMY_PERSONA,
    PERSONAS,
    build_prompt,
)
from app.services.rag.reflection_engine import (
    ReflectionEngine,
    verify_chemical_safety,
)
from app.services.rag.router import (
    build_diagnosis_query,
    extract_crop_context,
    plan_query,
    route_query,
)
from app.services.router_agent import RouterAgent


class FakeLLMClient:
    def __init__(self, response: str = "retrieve"):
        self.response = response
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


class TestCropExtraction:
    def test_extract_crop_simple(self):
        assert extract_crop_context("How do I manage early blight on tomato?") == "tomato"
        assert extract_crop_context("What is the fungicide for peach scab?") == "peach"
        assert extract_crop_context("Tell me about potato late blight control") == "potato"
        assert extract_crop_context("Is corn leaf spot dangerous?") == "corn"
        assert extract_crop_context("My strawberry leaves have brown spots") == "strawberry"
        assert extract_crop_context("Cedar apple rust treatment") == "apple"

    def test_extract_crop_case_insensitive_and_punctuation(self):
        assert extract_crop_context("TOMATOES: yellow curling leaves!") == "tomato"
        assert extract_crop_context("Treating cherries with powdery mildew.") == "cherry"
        assert extract_crop_context("Bell pepper anthracnose symptoms") == "bell pepper"

    def test_extract_crop_none_when_unrelated(self):
        assert extract_crop_context("What is our Q3 revenue forecast?") is None
        assert extract_crop_context("Hello there!") is None
        assert extract_crop_context(None) is None


class TestBuildDiagnosisQuery:
    def test_build_diagnosis_query_with_prediction_crop(self):
        prediction = VisionPrediction(
            raw_class="Tomato___Early_blight",
            crop="tomato",
            disease="early blight",
            confidence=0.98,
            low_confidence=False,
        )
        query = build_diagnosis_query(prediction, user_query="what fungicide to use?")
        assert "early blight on tomato" in query
        assert "what fungicide to use?" in query

    def test_build_diagnosis_query_with_collection_override(self):
        prediction = VisionPrediction(
            raw_class="Peach___Bacterial_spot",
            crop="peach",
            disease="bacterial spot",
            confidence=0.95,
            low_confidence=False,
        )
        query = build_diagnosis_query(prediction, collection="peach")
        assert query == "bacterial spot on peach"

    def test_build_diagnosis_query_healthy(self):
        prediction = VisionPrediction(
            raw_class="Tomato___healthy",
            crop="tomato",
            disease="healthy",
            confidence=0.99,
            low_confidence=False,
        )
        query = build_diagnosis_query(prediction)
        assert query == "healthy tomato"


class TestQueryRouterAndPlanDecision:
    def test_plan_query_extracts_crop_and_collection(self):
        plan = plan_query("How to treat tomato powdery mildew?")
        assert plan.action == "retrieve"
        assert plan.crop == "tomato"
        assert plan.collection == "tomato"

    def test_route_query_conversational_retains_crop_when_present(self):
        plan = route_query("hello")
        assert plan.action == "conversational"

        plan_with_crop = plan_query("What is wrong with my tomato plant?")
        assert plan_with_crop.crop == "tomato"
        assert plan_with_crop.collection == "tomato"

    def test_router_agent_decide_extracts_crop_and_collection(self):
        router = RouterAgent(FakeLLMClient(response="retrieve"), fallback_planner=plan_query)
        decision = router.decide("What is causing dark spots on my potato leaves?")
        assert decision.action == "retrieve"
        assert decision.crop == "potato"
        assert decision.collection == "potato"

    def test_router_agent_llm_path_preserves_crop(self):
        llm = FakeLLMClient(response="retrieve")
        router = RouterAgent(llm, fallback_planner=plan_query)
        decision = router.decide("What is the harvest schedule for sweet corn?")
        assert decision.crop == "corn"
        assert decision.collection == "corn"


class TestAgronomyPromptPersona:
    def test_agronomy_persona_registered_in_personas(self):
        assert "agronomist" in PERSONAS
        assert "agronomy" in PERSONAS
        assert "plant_pathologist" in PERSONAS
        assert "diagnosis" in PERSONAS
        assert PERSONAS["agronomist"] == AGRONOMY_PERSONA

    def test_agronomy_persona_contains_all_six_sections(self):
        sections = [
            "1. **Visual Diagnosis & Severity Assessment**",
            "2. **Field Protocol & Maintenance Schedule**",
            "3. **Organic & Biological Control Remedies (OMRI approved options)**",
            "4. **Chemical Controls & Dosage Protocols**",
            "5. **Long-Term Cultural Practices & Field Sanitation**",
            "6. **Grounded University Extension Citations**",
        ]
        for section in sections:
            assert section in AGRONOMY_PERSONA

    def test_agronomy_persona_contains_safety_mandate(self):
        assert "SAFETY MANDATE" in AGRONOMY_PERSONA
        assert "PPE" in AGRONOMY_PERSONA
        assert "REI" in AGRONOMY_PERSONA
        assert "PHI" in AGRONOMY_PERSONA

    def test_build_prompt_with_agronomy_persona(self):
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                document_id="d1",
                text="Chlorothalonil is effective for early blight control at 1.5 pt/acre.",
                score=0.92,
                metadata={"title": "Tomato Disease Guide"},
            )
        ]
        prompt = build_prompt(
            "How to treat tomato early blight?",
            chunks=chunks,
            persona="agronomist",
        )
        assert "Plant Pathology & Agronomy Expert Persona" in prompt
        assert "Field Protocol & Maintenance Schedule" in prompt
        assert "Chlorothalonil" in prompt


class TestChemicalSafetyReflectionVerification:
    def test_verify_chemical_safety_passes_without_chemicals(self):
        # Non-chemical advice doesn't require PPE/REI/PHI cautions
        answer = "Prune lower infected leaves, improve air circulation, and apply compost tea."
        assert verify_chemical_safety(answer) is True

    def test_verify_chemical_safety_fails_when_chemicals_lack_cautions(self):
        # Chemical active ingredients mentioned without safety caution
        unsafe_answer = (
            "Apply chlorothalonil at 1.5 pt/acre or azoxystrobin every 7-10 days to arrest pathogen spread."
        )
        assert verify_chemical_safety(unsafe_answer) is False

    def test_verify_chemical_safety_passes_when_ppe_or_precautions_present(self):
        safe_answer_1 = (
            "Apply chlorothalonil at 1.5 pt/acre. Wear appropriate PPE (chemical-resistant gloves and eye protection). "
            "Observe a 12-hour REI and 0-day PHI according to EPA label instructions."
        )
        assert verify_chemical_safety(safe_answer_1) is True

        safe_answer_2 = (
            "Use copper hydroxide spray. Caution: Wear protective clothing and follow label directions."
        )
        assert verify_chemical_safety(safe_answer_2) is True

    def test_reflection_engine_verify_chemical_safety_method(self):
        engine = ReflectionEngine(FakeLLMClient())
        assert engine.verify_chemical_safety("Normal cultural practices [1].") is True
        assert engine.verify_chemical_safety("Spray mancozeb weekly.") is False
        assert engine.verify_chemical_safety("Spray mancozeb weekly. Follow label PPE precautions.") is True
