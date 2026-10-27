"""Eval dataset: 5 buyer profiles over the seed listings (Person C).

    python -m evals.dataset        # create/update the LangSmith dataset
"""

from __future__ import annotations

DATASET_NAME = "munich-home-buying-profiles"
RATE_PCT = 3.7  # pinned in the prompt and equal to the finance tool's offline fallback
YEARS = 30

PROFILES = [
    {"name": "young-couple", "budget": 750_000, "equity": 200_000, "max_monthly": 2_800,
     "rooms_min": 2, "rooms_max": 3, "districts": ["Schwabing", "Maxvorstadt"], "must_haves": ["balcony"]},
    {"name": "family", "budget": 1_100_000, "equity": 350_000, "max_monthly": 4_000,
     "rooms_min": 4, "rooms_max": 5, "districts": ["Trudering", "Pasing"], "must_haves": ["elevator or ground floor"]},
    {"name": "first-time-solo", "budget": 600_000, "equity": 150_000, "max_monthly": 2_400,
     "rooms_min": 2, "rooms_max": 2, "districts": ["Sendling"], "must_haves": []},
    {"name": "upgrader", "budget": 1_600_000, "equity": 600_000, "max_monthly": 5_500,
     "rooms_min": 3, "rooms_max": 4, "districts": ["Schwabing"], "must_haves": ["terrace"]},
    {"name": "renovator", "budget": 700_000, "equity": 180_000, "max_monthly": 2_900,
     "rooms_min": 3, "rooms_max": 3, "districts": [], "must_haves": ["open to renovation"]},
]


def example(profile: dict) -> tuple[dict, dict]:
    """(inputs, reference_outputs) for one profile; the references pin the finance check."""
    return profile, {
        "equity": profile["equity"],
        "max_monthly": profile["max_monthly"],
        "rate_pct": RATE_PCT,
        "years": YEARS,
    }


def interview_message(profile: dict, user_id: str) -> str:
    districts = ", ".join(profile["districts"]) or "any Munich district"
    musts = ", ".join(profile["must_haves"]) or "none"
    return (
        f"Hi, my user_id is {user_id}. I want to buy an apartment in Munich. "
        f"Budget EUR {profile['budget']:,}, equity EUR {profile['equity']:,}, "
        f"maximum monthly payment EUR {profile['max_monthly']:,}. "
        f"{profile['rooms_min']}-{profile['rooms_max']} rooms, districts: {districts}. Must-haves: {musts}. "
        f"Assume a {RATE_PCT}% interest rate over {YEARS} years for all finance calculations. "
        "That is everything you need: save my profile, search, evaluate every candidate and give me a ranked shortlist."
    )


def create_dataset(client=None, name: str = DATASET_NAME) -> str:
    from langsmith import Client

    client = client or Client()
    if client.has_dataset(dataset_name=name):
        return f"dataset {name!r} already exists"
    ds = client.create_dataset(name, description="Buyer profiles for the Munich home-buying agent evals")
    pairs = [example(p) for p in PROFILES]
    client.create_examples(
        dataset_id=ds.id, inputs=[i for i, _ in pairs], outputs=[o for _, o in pairs]
    )
    return f"created dataset {name!r} with {len(pairs)} examples"


if __name__ == "__main__":
    import agent.config  # noqa: F401  (loads .env)

    print(create_dataset())
