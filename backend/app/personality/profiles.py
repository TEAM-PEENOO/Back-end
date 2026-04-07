from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalityProfile:
    learning_gain: float
    memory_bonus: float
    retention_multiplier: float
    pass_combined: int
    pass_user_min: int
    pass_persona_min: int


PROFILES: dict[str, PersonalityProfile] = {
    "curious": PersonalityProfile(
        learning_gain=1.0,
        memory_bonus=1.0,
        retention_multiplier=1.0,
        pass_combined=75,
        pass_user_min=50,
        pass_persona_min=30,
    ),
    "careful": PersonalityProfile(
        learning_gain=0.9,
        memory_bonus=1.15,
        retention_multiplier=1.15,
        pass_combined=70,
        pass_user_min=50,
        pass_persona_min=30,
    ),
    "clumsy": PersonalityProfile(
        learning_gain=1.05,
        memory_bonus=0.8,
        retention_multiplier=0.8,
        pass_combined=80,
        pass_user_min=50,
        pass_persona_min=30,
    ),
    "perfectionist": PersonalityProfile(
        learning_gain=1.0,
        memory_bonus=1.05,
        retention_multiplier=1.0,
        pass_combined=85,
        pass_user_min=55,
        pass_persona_min=35,
    ),
    # New type: slower initial learning, but longer memory retention.
    "steady": PersonalityProfile(
        learning_gain=0.75,
        memory_bonus=1.35,
        retention_multiplier=1.3,
        pass_combined=72,
        pass_user_min=50,
        pass_persona_min=30,
    ),
}


def profile_for(personality: str) -> PersonalityProfile:
    return PROFILES.get(personality, PROFILES["curious"])

