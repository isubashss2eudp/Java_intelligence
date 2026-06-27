"""
User profile collection and knowledge-level computation.

Prompts the user one-by-one for:
  - Name (free text)
  - Role
  - Programming knowledge
  - Java expertise
  - Purpose of analysis
  - Expected depth

All choice fields display the accepted values BEFORE the user types,
so the user only needs to enter a number.

The collected answers are combined into a composite score that maps to
one of four knowledge levels:

  beginner     (score 0-3)   -- Executive / Functional overview
  intermediate (score 4-6)   -- Technical overview
  advanced     (score 7-9)   -- Deep technical analysis
  expert       (score 10-11) -- Expert-level analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Accepted values — displayed in the CLI before the user enters a choice
# ---------------------------------------------------------------------------

ROLES: List[str] = [
    "Developer",
    "Senior Developer",
    "Tech Lead",
    "Architect",
    "Engineering Manager",
    "QA",
    "DevOps",
    "Product Owner",
    "New Joiner",
]

PROGRAMMING_KNOWLEDGE: List[str] = [
    "Beginner",
    "Intermediate",
    "Advanced",
]

JAVA_EXPERTISE: List[str] = [
    "Beginner",
    "Intermediate",
    "Advanced",
    "Expert",
]

PURPOSES: List[str] = [
    "High-Level Overview",
    "Technical Specification",
    "Knowledge Transfer",
    "Onboarding",
    "Code Review",
    "Bug Investigation",
    "Migration Assessment",
    "Architecture Assessment",
    "Security Review",
    "Performance Review",
    "Dependency Analysis",
]

DEPTHS: List[str] = [
    "Executive Summary",
    "Functional Overview",
    "Technical Overview",
    "Deep Technical Analysis",
    "Expert Level Analysis",
]


# ---------------------------------------------------------------------------
# Knowledge-level scoring tables
# ---------------------------------------------------------------------------

_ROLE_SCORES = {
    "New Joiner":          0,
    "Product Owner":       0,
    "Developer":           1,
    "QA":                  1,
    "DevOps":              1,
    "Senior Developer":    2,
    "Engineering Manager": 2,
    "Tech Lead":           3,
    "Architect":           4,
}

_JAVA_SCORES = {
    "Beginner":    0,
    "Intermediate": 1,
    "Advanced":    2,
    "Expert":      3,
}

_DEPTH_SCORES = {
    "Executive Summary":       0,
    "Functional Overview":     1,
    "Technical Overview":      2,
    "Deep Technical Analysis": 3,
    "Expert Level Analysis":   4,
}

# Composite score → knowledge level
# Max possible: 4 (role) + 3 (java) + 4 (depth) = 11
_THRESHOLDS = [
    (3,  "beginner"),     # 0 – 3
    (6,  "intermediate"), # 4 – 6
    (9,  "advanced"),     # 7 – 9
    (11, "expert"),       # 10 – 11
]


# ---------------------------------------------------------------------------
# UserProfile dataclass
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """Collected user profile with a computed knowledge level."""

    name:                  str
    role:                  str
    programming_knowledge: str
    java_expertise:        str
    purpose:               str
    depth:                 str
    knowledge_level:       str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.knowledge_level = _compute_level(self)

    def describe(self) -> str:
        """Return a formatted multi-line string summarising the profile."""
        level_labels = {
            "beginner":     "Beginner",
            "intermediate": "Intermediate",
            "advanced":     "Advanced",
            "expert":       "Expert",
        }
        return (
            f"  Name                  : {self.name}\n"
            f"  Role                  : {self.role}\n"
            f"  Programming knowledge : {self.programming_knowledge}\n"
            f"  Java expertise        : {self.java_expertise}\n"
            f"  Purpose               : {self.purpose}\n"
            f"  Expected depth        : {self.depth}\n"
            f"  Knowledge level       : {level_labels.get(self.knowledge_level, 'Intermediate')}"
        )


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def _compute_level(profile: UserProfile) -> str:
    """Map a UserProfile to one of the four knowledge levels."""
    total = (
        _ROLE_SCORES.get(profile.role, 1)
        + _JAVA_SCORES.get(profile.java_expertise, 1)
        + _DEPTH_SCORES.get(profile.depth, 1)
    )
    for threshold, level in _THRESHOLDS:
        if total <= threshold:
            return level
    return "expert"


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _prompt_choice(prompt: str, options: List[str]) -> str:
    """
    Display numbered options, then prompt the user to enter a number.
    Loops until a valid choice is made.
    """
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i:>2}. {opt}")
    while True:
        try:
            raw = input(f"\n  Enter choice (1-{len(options)}): ").strip()
            idx = int(raw)
            if 1 <= idx <= len(options):
                selected = options[idx - 1]
                print(f"       → {selected}")
                return selected
        except (ValueError, EOFError):
            pass
        print(f"  Please enter a number between 1 and {len(options)}.")


def _prompt_name() -> str:
    """Prompt for a non-empty name."""
    while True:
        try:
            name = input("\nYour Name: ").strip()
        except EOFError:
            name = "User"
        if name:
            print(f"       → {name}")
            return name
        print("  Name cannot be empty. Please try again.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_user_profile() -> UserProfile:
    """
    Interactively collect a user profile from stdin.

    Each field displays the accepted values before asking for input so
    the user enters a number rather than free text (except for the name).

    Returns
    -------
    UserProfile
        Fully populated profile with a computed knowledge_level.
    """
    print("\n" + "=" * 62)
    print("  RetroDecrypt Platform — User Profiling")
    print("=" * 62)
    print(
        "  Please answer the following questions.\n"
        "  Personalised documentation will be generated based on\n"
        "  your background and the depth of analysis you need.\n"
    )

    name                  = _prompt_name()
    role                  = _prompt_choice("Your Role:", ROLES)
    programming_knowledge = _prompt_choice("Your Programming Knowledge:", PROGRAMMING_KNOWLEDGE)
    java_expertise        = _prompt_choice("Your Java Expertise:", JAVA_EXPERTISE)
    purpose               = _prompt_choice("Purpose of Analysis:", PURPOSES)
    depth                 = _prompt_choice("Expected Depth:", DEPTHS)

    profile = UserProfile(
        name=name,
        role=role,
        programming_knowledge=programming_knowledge,
        java_expertise=java_expertise,
        purpose=purpose,
        depth=depth,
    )

    print("\n" + "-" * 62)
    print("  Profile Summary")
    print("-" * 62)
    print(profile.describe())
    print("-" * 62)

    return profile
