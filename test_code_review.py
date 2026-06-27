"""
Phase 8: Code Review Intelligence -- comprehensive test suite.

Tests cover:
  - All individual analyzer modules (SOLID, security, performance, maintainability,
    duplicates, tech_debt, patterns)
  - CodeReviewEngine orchestration
  - Report generation (text + JSON)
  - Score calculation and grading
  - Agent tool registration

Run with: pytest test_code_review.py -v
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.code_review.models import (
    CategorySummary,
    CodeReviewReport,
    FindingCategory,
    ReviewFinding,
    Severity,
    SEVERITY_WEIGHTS,
)
from src.code_review.engine import (
    CodeReviewEngine,
    _compute_score,
    _grade,
    _build_category_summaries,
    _top_issues,
    _deduplicate,
)
from src.code_review.analyzers.solid import analyze_solid
from src.code_review.analyzers.security import analyze_security
from src.code_review.analyzers.performance import analyze_performance
from src.code_review.analyzers.maintainability import analyze_maintainability
from src.code_review.analyzers.duplicates import analyze_duplicates
from src.code_review.analyzers.tech_debt import analyze_tech_debt
from src.code_review.analyzers.patterns import analyze_patterns


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_metadata(
    file_path: str = "com/example/TestService.java",
    classes: List[str] = None,
    interfaces: List[str] = None,
    methods: List[str] = None,
    imports: List[str] = None,
    annotations: List[str] = None,
    loc: int = 100,
) -> dict:
    return {
        "file_path":     file_path,
        "package":       "com.example",
        "classes":       classes or ["TestService"],
        "interfaces":    interfaces or [],
        "methods":       methods or ["getUser", "saveUser"],
        "imports":       imports or [],
        "annotations":   annotations or ["Service"],
        "lines_of_code": loc,
        "content_hash":  "abc123",
    }


# Small synthetic Java snippets for content-based tests
_FIELD_INJECTION_JAVA = """\
@Service
public class OrderService {
    @Autowired
    private UserRepository userRepository;

    @Autowired
    private EmailService emailService;

    public Order createOrder(Long userId) {
        return new Order(userId);
    }
}
"""

_SQL_INJECTION_JAVA = """\
@Repository
public class CustomerRepository {
    public Customer find(String name) {
        String query = "SELECT * FROM customers WHERE name = '" + name + "'";
        return em.createNativeQuery(query).getSingleResult();
    }
}
"""

_HARDCODED_CRED_JAVA = """\
@Configuration
public class DatabaseConfig {
    private String password = "super_secret_password123";
    private String apiKey = "sk-prod-abc123xyz789";
}
"""

_N_PLUS_ONE_JAVA = """\
@Service
public class ReportService {
    public List<OrderDTO> buildReport() {
        List<Long> ids = getIds();
        List<OrderDTO> result = new ArrayList<>();
        for (Long id : ids) {
            Order o = orderRepository.findById(id).orElseThrow();
            result.add(toDTO(o));
        }
        return result;
    }
}
"""

_EMPTY_CATCH_JAVA = """\
@Service
public class PaymentService {
    public void processPayment(Payment p) {
        try {
            gateway.charge(p);
        } catch (GatewayException e) {
        }
    }
}
"""

_TODO_JAVA = """\
@Service
public class NotificationService {
    // TODO: implement retry logic
    // FIXME: this breaks for international numbers
    // HACK: temporary workaround for timezone issue
    // TODO: remove hardcoded delay
    // FIXME: null check missing
    public void send(String message) {
        System.out.println(message);
    }
}
"""

_GOD_CLASS_JAVA = """\
@Service
public class MegaService {
""" + "\n".join(
    f"    public void method{i}() {{ }}"
    for i in range(25)
) + "\n}\n"

_UNSUPPORTED_JAVA = """\
public class PartialImpl implements FullInterface {
    @Override
    public void doA() { /* impl */ }

    @Override
    public void doB() {
        throw new UnsupportedOperationException("not supported");
    }
}
"""

_WEAK_CRYPTO_JAVA = """\
@Component
public class HashUtil {
    public String hash(String input) {
        MessageDigest md = MessageDigest.getInstance("MD5");
        return new String(md.digest(input.getBytes()));
    }
}
"""


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestModels:
    def test_severity_ordering(self):
        assert Severity.CRITICAL != Severity.HIGH
        assert list(Severity) == [
            Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
            Severity.LOW, Severity.INFO,
        ]

    def test_finding_to_dict(self):
        f = ReviewFinding(
            category=FindingCategory.SECURITY,
            severity=Severity.CRITICAL,
            rule_id="SEC-001",
            title="SQL Injection",
            description="SQL injection risk",
            recommendation="Use parameterised queries",
            affected_files=["Foo.java"],
            affected_classes=["FooRepository"],
            evidence="SELECT * FROM t WHERE id = '" + "+ id",
        )
        d = f.to_dict()
        assert d["rule_id"] == "SEC-001"
        assert d["severity"] == "critical"
        assert d["category"] == "security"
        assert len(d["evidence"]) <= 500

    def test_report_to_json(self):
        f = ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.MEDIUM,
            rule_id="SOLID-S001",
            title="SRP violation",
            description="Too many methods",
            recommendation="Split the class",
        )
        report = CodeReviewReport(
            repository_path="/repo",
            reviewed_files=10,
            total_classes=20,
            total_findings=1,
            findings=[f],
            quality_score=85.0,
            grade="B",
            summary="Good overall",
        )
        d = report.to_json_report()
        assert d["quality_score"] == 85.0
        assert d["grade"] == "B"
        assert len(d["findings"]) == 1

    def test_report_text_format(self):
        f = ReviewFinding(
            category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            rule_id="SEC-002",
            title="Hardcoded credential",
            description="Password in source",
            recommendation="Use env var",
            affected_classes=["Config"],
        )
        report = CodeReviewReport(
            repository_path="/repo",
            reviewed_files=5,
            total_classes=10,
            total_findings=1,
            findings=[f],
            quality_score=70.0,
            grade="C",
            summary="Security issues found",
        )
        text = report.to_text_report()
        assert "CODE REVIEW REPORT" in text
        assert "SEC-002" in text
        assert "Grade: C" in text

    def test_findings_by_severity(self):
        findings = [
            ReviewFinding(
                category=FindingCategory.SOLID, severity=Severity.HIGH,
                rule_id="X", title="x", description="d", recommendation="r"
            ),
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.CRITICAL,
                rule_id="Y", title="y", description="d", recommendation="r"
            ),
        ]
        report = CodeReviewReport(
            repository_path=".", reviewed_files=1, total_classes=1,
            total_findings=2, findings=findings,
        )
        assert len(report.findings_by_severity(Severity.HIGH)) == 1
        assert len(report.findings_by_severity(Severity.CRITICAL)) == 1


# ---------------------------------------------------------------------------
# Engine / score tests
# ---------------------------------------------------------------------------

class TestEngineScoring:
    def test_perfect_score_no_findings(self):
        assert _compute_score([], 10) == 100.0

    def test_score_penalised_by_critical(self):
        findings = [
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.CRITICAL,
                rule_id="X", title="x", description="d", recommendation="r"
            )
        ] * 5
        score = _compute_score(findings, 10)
        assert score < 100.0

    def test_grade_thresholds(self):
        assert _grade(95.0) == "A"
        assert _grade(80.0) == "B"
        assert _grade(65.0) == "C"
        assert _grade(50.0) == "D"
        assert _grade(30.0) == "F"

    def test_category_summaries_aggregation(self):
        findings = [
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.CRITICAL,
                rule_id="S1", title="t", description="d", recommendation="r"
            ),
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.HIGH,
                rule_id="S2", title="t", description="d", recommendation="r"
            ),
            ReviewFinding(
                category=FindingCategory.SOLID, severity=Severity.MEDIUM,
                rule_id="S3", title="t", description="d", recommendation="r"
            ),
        ]
        summaries = _build_category_summaries(findings)
        sec = next(s for s in summaries if s.category == FindingCategory.SECURITY)
        assert sec.total == 2
        assert sec.critical == 1
        assert sec.high == 1

    def test_deduplication(self):
        f1 = ReviewFinding(
            category=FindingCategory.SOLID, severity=Severity.MEDIUM,
            rule_id="SOLID-S001", title="t", description="d",
            recommendation="r", affected_classes=["Foo"],
        )
        f2 = ReviewFinding(
            category=FindingCategory.SOLID, severity=Severity.MEDIUM,
            rule_id="SOLID-S001", title="t", description="d",
            recommendation="r", affected_classes=["Foo"],
        )
        result = _deduplicate([f1, f2])
        assert len(result) == 1

    def test_top_issues_ordering(self):
        findings = [
            ReviewFinding(
                category=FindingCategory.SOLID, severity=Severity.LOW,
                rule_id="A", title="Low issue", description="d", recommendation="r"
            ),
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.CRITICAL,
                rule_id="B", title="Critical issue", description="d", recommendation="r"
            ),
        ]
        top = _top_issues(findings, 5)
        assert top[0].startswith("[CRITICAL]")


# ---------------------------------------------------------------------------
# SOLID analyser tests
# ---------------------------------------------------------------------------

class TestSolidAnalyzer:
    def _meta_with_content(self, content: str, **kwargs) -> dict:
        """Build metadata dict with an in-memory file mock."""
        return {
            "file_path":     "TestClass.java",
            "classes":       kwargs.get("classes", ["TestClass"]),
            "interfaces":    kwargs.get("interfaces", []),
            "methods":       kwargs.get("methods", ["method1"]),
            "imports":       kwargs.get("imports", []),
            "annotations":   kwargs.get("annotations", []),
            "lines_of_code": kwargs.get("loc", 50),
        }

    def test_srp_too_many_methods(self):
        meta = _make_metadata(
            methods=[f"method{i}" for i in range(20)],
            loc=400,
        )
        with patch("src.code_review.analyzers.solid._read_file", return_value=""):
            findings = analyze_solid([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SOLID-S001" in rule_ids

    def test_srp_large_class(self):
        meta = _make_metadata(loc=400)
        with patch("src.code_review.analyzers.solid._read_file", return_value=""):
            findings = analyze_solid([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SOLID-S002" in rule_ids

    def test_dip_field_injection(self):
        meta = _make_metadata()
        with patch("src.code_review.analyzers.solid._read_file",
                   return_value=_FIELD_INJECTION_JAVA):
            findings = analyze_solid([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SOLID-D001" in rule_ids

    def test_lsp_unsupported_operation(self):
        meta = _make_metadata()
        with patch("src.code_review.analyzers.solid._read_file",
                   return_value=_UNSUPPORTED_JAVA):
            findings = analyze_solid([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SOLID-L001" in rule_ids

    def test_no_violations_clean_class(self):
        meta = _make_metadata(
            methods=["getUser", "saveUser"],
            loc=50,
        )
        with patch("src.code_review.analyzers.solid._read_file", return_value=""):
            findings = analyze_solid([meta])
        # Small clean class should produce no/minimal findings
        assert all(f.severity in (Severity.LOW, Severity.INFO) for f in findings)


# ---------------------------------------------------------------------------
# Security analyser tests
# ---------------------------------------------------------------------------

class TestSecurityAnalyzer:
    def _meta(self, annotations=None) -> dict:
        return _make_metadata(annotations=annotations or ["Repository"])

    def test_sql_injection_detected(self):
        meta = self._meta()
        with patch("src.code_review.analyzers.security._read_file",
                   return_value=_SQL_INJECTION_JAVA):
            findings = analyze_security([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SEC-001" in rule_ids
        crit = next(f for f in findings if f.rule_id == "SEC-001")
        assert crit.severity == Severity.CRITICAL

    def test_hardcoded_credentials_detected(self):
        meta = _make_metadata(annotations=["Configuration"])
        with patch("src.code_review.analyzers.security._read_file",
                   return_value=_HARDCODED_CRED_JAVA):
            findings = analyze_security([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SEC-002" in rule_ids

    def test_weak_crypto_detected(self):
        meta = _make_metadata(annotations=["Component"])
        with patch("src.code_review.analyzers.security._read_file",
                   return_value=_WEAK_CRYPTO_JAVA):
            findings = analyze_security([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "SEC-005" in rule_ids

    def test_clean_service_no_critical_security(self):
        meta = _make_metadata(annotations=["Service"])
        clean_java = """\
@Service
public class CleanService {
    private final UserRepository repo;
    public CleanService(UserRepository repo) { this.repo = repo; }
    public User find(Long id) { return repo.findById(id).orElseThrow(); }
}
"""
        with patch("src.code_review.analyzers.security._read_file",
                   return_value=clean_java):
            findings = analyze_security([meta])
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0


# ---------------------------------------------------------------------------
# Performance analyser tests
# ---------------------------------------------------------------------------

class TestPerformanceAnalyzer:
    def test_n_plus_one_detected(self):
        meta = _make_metadata(annotations=["Service"])
        with patch("src.code_review.analyzers.performance._read_file",
                   return_value=_N_PLUS_ONE_JAVA):
            findings = analyze_performance([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "PERF-001" in rule_ids

    def test_unbounded_find_all(self):
        meta = _make_metadata(annotations=["Service"])
        java = """\
@Service
public class ProductService {
    public List<Product> getAll() {
        return productRepository.findAll();
    }
}
"""
        with patch("src.code_review.analyzers.performance._read_file",
                   return_value=java):
            findings = analyze_performance([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "PERF-003" in rule_ids

    def test_eager_fetch_detected(self):
        meta = _make_metadata(annotations=["Entity"])
        java = """\
@Entity
public class Order {
    @OneToMany(fetch = FetchType.EAGER, cascade = CascadeType.ALL)
    private List<OrderItem> items;
}
"""
        with patch("src.code_review.analyzers.performance._read_file",
                   return_value=java):
            findings = analyze_performance([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "PERF-004" in rule_ids


# ---------------------------------------------------------------------------
# Maintainability analyser tests
# ---------------------------------------------------------------------------

class TestMaintainabilityAnalyzer:
    def test_empty_catch_detected(self):
        meta = _make_metadata(annotations=["Service"])
        with patch("src.code_review.analyzers.maintainability._read_file",
                   return_value=_EMPTY_CATCH_JAVA):
            findings = analyze_maintainability([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "MAINT-004" in rule_ids

    def test_deep_nesting_detected(self):
        meta = _make_metadata(annotations=["Service"])
        deep_java = (
            "public class Foo {\n"
            "    public void m() {\n"
            "        if (a) {\n"
            "            if (b) {\n"
            "                if (c) {\n"
            "                    if (d) {\n"
            "                        if (e) {\n"
            "                            doSomething();\n"
            "                        }\n"
            "                    }\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        with patch("src.code_review.analyzers.maintainability._read_file",
                   return_value=deep_java):
            findings = analyze_maintainability([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "MAINT-002" in rule_ids

    def test_public_fields_detected(self):
        meta = _make_metadata()
        java = """\
public class Config {
    public String host = "localhost";
    public int port = 8080;
    public boolean debug = false;
}
"""
        with patch("src.code_review.analyzers.maintainability._read_file",
                   return_value=java):
            findings = analyze_maintainability([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "MAINT-010" in rule_ids


# ---------------------------------------------------------------------------
# Technical debt tests
# ---------------------------------------------------------------------------

class TestTechDebtAnalyzer:
    def test_todo_comments_detected(self):
        meta = _make_metadata(annotations=["Service"])
        with patch("src.code_review.analyzers.tech_debt._read_file",
                   return_value=_TODO_JAVA):
            findings = analyze_tech_debt([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "DEBT-001" in rule_ids

    def test_todo_count_affects_severity(self):
        meta = _make_metadata(annotations=["Service"])
        with patch("src.code_review.analyzers.tech_debt._read_file",
                   return_value=_TODO_JAVA):
            findings = analyze_tech_debt([meta])
        debt_findings = [f for f in findings if f.rule_id == "DEBT-001"]
        assert debt_findings[0].severity in (Severity.MEDIUM, Severity.LOW)

    def test_missing_test_class_detected(self):
        """Service class without a corresponding test class should be flagged."""
        meta_service = _make_metadata(
            file_path="OrderService.java",
            classes=["OrderService"],
            annotations=["Service"],
        )
        # No test class in metadata
        with patch("src.code_review.analyzers.tech_debt._read_file", return_value=""):
            findings = analyze_tech_debt([meta_service])
        rule_ids = [f.rule_id for f in findings]
        assert "DEBT-007" in rule_ids

    def test_missing_test_not_flagged_when_test_exists(self):
        meta_service = _make_metadata(
            file_path="OrderService.java",
            classes=["OrderService"],
            annotations=["Service"],
        )
        meta_test = _make_metadata(
            file_path="OrderServiceTest.java",
            classes=["OrderServiceTest"],
            annotations=[],
        )
        with patch("src.code_review.analyzers.tech_debt._read_file", return_value=""):
            findings = analyze_tech_debt([meta_service, meta_test])
        debt_007 = [f for f in findings if f.rule_id == "DEBT-007"]
        assert len(debt_007) == 0


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------

class TestDuplicateAnalyzer:
    def test_structural_clone_detected(self):
        """Two classes with high method similarity should be flagged as clones."""
        method_set = [f"method{i}" for i in range(10)]
        meta_a = _make_metadata(
            file_path="ServiceA.java",
            classes=["ServiceA"],
            methods=method_set,
        )
        meta_b = _make_metadata(
            file_path="ServiceB.java",
            classes=["ServiceB"],
            methods=method_set,  # identical
        )
        # Patch content to return valid method signatures for both files
        common_java = "\n".join(
            f"public void {m}() {{}}" for m in method_set
        )
        with patch("src.code_review.analyzers.duplicates._read_file",
                   return_value=common_java):
            findings = analyze_duplicates([meta_a, meta_b])
        rule_ids = [f.rule_id for f in findings]
        assert "DUP-002" in rule_ids


# ---------------------------------------------------------------------------
# Pattern detection tests
# ---------------------------------------------------------------------------

class TestPatternAnalyzer:
    def test_god_class_detected(self):
        meta = _make_metadata(
            classes=["MegaService"],
            methods=[f"method{i}" for i in range(25)],
            loc=600,
            annotations=["Service"],
        )
        with patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            findings = analyze_patterns([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "ANTI-001" in rule_ids

    def test_service_locator_detected(self):
        java = """\
@Service
public class BadService {
    @Autowired
    private ApplicationContext applicationContext;

    public void doSomething() {
        UserService us = (UserService) applicationContext.getBean("userService");
    }
}
"""
        meta = _make_metadata(annotations=["Service"])
        with patch("src.code_review.analyzers.patterns._read_file", return_value=java):
            findings = analyze_patterns([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "ANTI-002" in rule_ids

    def test_anemic_entity_detected(self):
        meta = _make_metadata(
            classes=["User"],
            annotations=["Entity"],
            methods=["getId", "getName", "setId", "setName"],
        )
        with patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            findings = analyze_patterns([meta])
        rule_ids = [f.rule_id for f in findings]
        assert "ANTI-003" in rule_ids


# ---------------------------------------------------------------------------
# Engine integration tests
# ---------------------------------------------------------------------------

class TestCodeReviewEngine:
    def _build_metadata(self) -> List[dict]:
        return [
            _make_metadata(
                file_path="OrderService.java",
                classes=["OrderService"],
                methods=["createOrder", "cancelOrder"],
                annotations=["Service"],
                loc=100,
            ),
            _make_metadata(
                file_path="CustomerController.java",
                classes=["CustomerController"],
                methods=["getCustomer", "createCustomer"],
                annotations=["RestController"],
                loc=80,
            ),
        ]

    def test_engine_runs_all_analyzers(self):
        engine = CodeReviewEngine(repo_root="")
        metadata = self._build_metadata()
        with patch("src.code_review.analyzers.solid._read_file", return_value=""), \
             patch("src.code_review.analyzers.security._read_file", return_value=""), \
             patch("src.code_review.analyzers.performance._read_file", return_value=""), \
             patch("src.code_review.analyzers.maintainability._read_file", return_value=""), \
             patch("src.code_review.analyzers.duplicates._read_file", return_value=""), \
             patch("src.code_review.analyzers.tech_debt._read_file", return_value=""), \
             patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            report = engine.run(metadata)

        assert isinstance(report, CodeReviewReport)
        assert report.reviewed_files == 2
        assert report.total_classes == 2
        assert 0.0 <= report.quality_score <= 100.0
        assert report.grade in ("A", "B", "C", "D", "F")

    def test_engine_selective_analyzers(self):
        engine = CodeReviewEngine(repo_root="", enabled_analyzers=["security"])
        metadata = self._build_metadata()
        with patch("src.code_review.analyzers.security._read_file",
                   return_value=_HARDCODED_CRED_JAVA):
            report = engine.run(metadata)

        # Only security findings should be present
        categories = {f.category for f in report.findings}
        assert FindingCategory.SECURITY in categories or len(report.findings) == 0

    def test_engine_target_class_filter(self):
        engine = CodeReviewEngine(repo_root="")
        metadata = self._build_metadata()
        with patch("src.code_review.analyzers.solid._read_file", return_value=""), \
             patch("src.code_review.analyzers.security._read_file", return_value=""), \
             patch("src.code_review.analyzers.performance._read_file", return_value=""), \
             patch("src.code_review.analyzers.maintainability._read_file", return_value=""), \
             patch("src.code_review.analyzers.duplicates._read_file", return_value=""), \
             patch("src.code_review.analyzers.tech_debt._read_file", return_value=""), \
             patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            report = engine.run(metadata, target_classes=["OrderService"])

        # Only OrderService metadata should be in scope
        assert report.reviewed_files == 1

    def test_report_has_summary(self):
        engine = CodeReviewEngine(repo_root="")
        metadata = self._build_metadata()
        with patch("src.code_review.analyzers.solid._read_file", return_value=""), \
             patch("src.code_review.analyzers.security._read_file", return_value=""), \
             patch("src.code_review.analyzers.performance._read_file", return_value=""), \
             patch("src.code_review.analyzers.maintainability._read_file", return_value=""), \
             patch("src.code_review.analyzers.duplicates._read_file", return_value=""), \
             patch("src.code_review.analyzers.tech_debt._read_file", return_value=""), \
             patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            report = engine.run(metadata)

        assert report.summary  # not empty
        assert isinstance(report.generated_at, datetime)

    def test_json_report_serialisable(self):
        engine = CodeReviewEngine(repo_root="")
        metadata = self._build_metadata()
        with patch("src.code_review.analyzers.solid._read_file", return_value=""), \
             patch("src.code_review.analyzers.security._read_file", return_value=""), \
             patch("src.code_review.analyzers.performance._read_file", return_value=""), \
             patch("src.code_review.analyzers.maintainability._read_file", return_value=""), \
             patch("src.code_review.analyzers.duplicates._read_file", return_value=""), \
             patch("src.code_review.analyzers.tech_debt._read_file", return_value=""), \
             patch("src.code_review.analyzers.patterns._read_file", return_value=""):
            report = engine.run(metadata)

        json_data = report.to_json_report()
        # Must be fully JSON-serialisable
        serialised = json.dumps(json_data)
        assert isinstance(serialised, str)
        deserialised = json.loads(serialised)
        assert deserialised["reviewed_files"] == 2


# ---------------------------------------------------------------------------
# Agent tool registration tests
# ---------------------------------------------------------------------------

class TestAgentToolRegistration:
    def test_phase8_tools_in_all_tools(self):
        from src.agent.tools import ALL_TOOLS
        tool_names = [t.name for t in ALL_TOOLS]
        assert "review_code_quality"      in tool_names
        assert "analyze_solid_principles" in tool_names
        assert "detect_security_issues"   in tool_names
        assert "analyze_technical_debt"   in tool_names

    def test_phase8_tools_are_callable(self):
        from src.agent.tools import (
            review_code_quality,
            analyze_solid_principles,
            detect_security_issues,
            analyze_technical_debt,
        )
        # Tools should be LangChain tool objects with .name and .description
        for tool_obj in (
            review_code_quality,
            analyze_solid_principles,
            detect_security_issues,
            analyze_technical_debt,
        ):
            assert hasattr(tool_obj, "name")
            assert hasattr(tool_obj, "description")
            assert len(tool_obj.description) > 10


# ---------------------------------------------------------------------------
# Prompts tests
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_build_llm_review_prompt(self):
        from src.code_review.prompts import build_llm_review_prompt

        findings = [
            ReviewFinding(
                category=FindingCategory.SECURITY, severity=Severity.CRITICAL,
                rule_id="SEC-001", title="SQL Injection",
                description="desc", recommendation="rec",
                affected_classes=["Repo"],
            )
        ]
        snippets = {"Repo": "public class Repo { ... }"}
        prompt = build_llm_review_prompt(findings, snippets)

        assert "SEC-001" in prompt
        assert "SQL Injection" in prompt
        assert "Repo" in prompt
        assert "JSON" in prompt

    def test_parse_llm_findings_valid_json(self):
        from src.code_review.prompts import parse_llm_findings

        raw = json.dumps({
            "additional_findings": [
                {
                    "rule_id": "LLM-001",
                    "category": "security",
                    "severity": "high",
                    "title": "Missing null check",
                    "description": "Null pointer risk",
                    "recommendation": "Add null check",
                    "affected_classes": ["FooService"],
                }
            ]
        })
        result = parse_llm_findings(raw)
        assert len(result) == 1
        assert result[0].rule_id == "LLM-001"
        assert result[0].severity == Severity.HIGH

    def test_parse_llm_findings_malformed_json(self):
        from src.code_review.prompts import parse_llm_findings

        result = parse_llm_findings("not json at all !@#$")
        assert result == []

    def test_parse_llm_findings_empty_array(self):
        from src.code_review.prompts import parse_llm_findings

        result = parse_llm_findings(json.dumps({"additional_findings": []}))
        assert result == []
