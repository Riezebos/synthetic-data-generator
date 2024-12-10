import random
from typing import List

from distilabel.llms import InferenceEndpointsLLM
from distilabel.steps.tasks import (
    GenerateTextClassificationData,
    TextClassification,
    TextGeneration,
)
from pydantic import BaseModel, Field

from synthetic_dataset_generator.constants import BASE_URL, MODEL
from synthetic_dataset_generator.pipelines.base import _get_next_api_key
from synthetic_dataset_generator.utils import get_preprocess_labels

PROMPT_CREATION_PROMPT = """You are an AI assistant specialized in generating very precise text classification tasks for dataset creation.

Your should write a prompt following a the dataset description. Respond with the prompt and nothing else.

The prompt should follow the same style and structure as the following example prompts, clearly specifying the possible classification labels.

Make sure to always include all of the detailed information from the description and the context of the company that is provided.

Don't include the labels in the classification_task but only provide a high level description of the classification task.

If a label is composed of multiple words, use a hyphen to separate them. For example, 'smartphone-review', 'customer-service', 'product-quality'.:

Description: DavidMovieHouse is a cinema that has been in business for 10 years.
Output: {"classification_task": "The company DavidMovieHouse is a cinema that has been in business for 10 years and has had customers reviews. Classify the customer reviews as", "labels": ["positive", "negative"]}

Description: A dataset that focuses on creating neo-ludite discussions about technologies within the AI space.
Output: {"classification_task": "Neo-ludiite discussions about technologies within the AI space cover. Categorize the discussions into one of the following categories", "labels": ["tech-support", "tech-opposition"]}

Description: A dataset that covers the articles of a niche sports website called TheSportBlogs that focuses on female sports within the ballsport domain for the US market.
Output: {"classification_task": "TechSportBlogs is a niche sports website that focuses on female sports within the ballsport domain for the US market. Determine the category of based on the article using the following categories", "labels": ["basketball", "volleyball", "tennis", "hockey", "baseball", "soccer"]}

Description: A dataset covering customer reviews for an e-commerce website called Argilla that sells technology datasets within the open source Natural Language Processing space and has review with labels "data-quality", "data-accuracy", "customer-service", "price", "product-availability", "shipping-speed"
Output: {"classification_task": "A dataset covering customer reviews for an e-commerce website called Argilla that sells technology datasets within the open source Natural Language Processing space and has review with labels", "labels": ["data-quality", "data-accuracy", "customer-service", "price", "product-availability", "shipping-speed"]}

Description:
"""

DEFAULT_DATASET_DESCRIPTIONS = [
    "A dataset covering customer reviews for an e-commerce website.",
    "A dataset covering news articles about various topics.",
]


class TextClassificationTask(BaseModel):
    classification_task: str = Field(
        ...,
        title="classification_task",
        description="The classification task to be performed.",
    )

    labels: list[str] = Field(
        ...,
        title="Labels",
        description="The possible labels for the classification task.",
    )


class DatasetDescription(BaseModel):
    description: str = Field(
        ...,
        title="description",
        description="The description of the dataset.",
    )
    labels: list[str] = Field(
        ...,
        title="labels",
        description="The possible labels for the classification task.",
    )


def get_prompt_generator():
    prompt_generator = TextGeneration(
        llm=InferenceEndpointsLLM(
            api_key=_get_next_api_key(),
            model_id=MODEL,
            base_url=BASE_URL,
            structured_output={"format": "json", "schema": TextClassificationTask},
            generation_kwargs={
                "temperature": 0.8,
                "max_new_tokens": 2048,
                "do_sample": True,
            },
        ),
        system_prompt=PROMPT_CREATION_PROMPT,
        use_system_prompt=True,
    )
    prompt_generator.load()
    return prompt_generator


def get_textcat_generator(difficulty, clarity, temperature, is_sample):
    textcat_generator = GenerateTextClassificationData(
        llm=InferenceEndpointsLLM(
            model_id=MODEL,
            base_url=BASE_URL,
            api_key=_get_next_api_key(),
            generation_kwargs={
                "temperature": temperature,
                "max_new_tokens": 256 if is_sample else 2048,
                "do_sample": True,
                "top_k": 50,
                "top_p": 0.95,
            },
        ),
        difficulty=None if difficulty == "mixed" else difficulty,
        clarity=None if clarity == "mixed" else clarity,
        seed=random.randint(0, 2**32 - 1),
    )
    textcat_generator.load()
    return textcat_generator


def get_labeller_generator(system_prompt, labels, num_labels):
    labeller_generator = TextClassification(
        llm=InferenceEndpointsLLM(
            model_id=MODEL,
            base_url=BASE_URL,
            api_key=_get_next_api_key(),
            generation_kwargs={
                "temperature": 0.7,
                "max_new_tokens": 2048,
            },
        ),
        context=system_prompt,
        available_labels=labels,
        n=num_labels,
        default_label="unknown",
    )
    labeller_generator.load()
    return labeller_generator


def generate_pipeline_code(
    system_prompt: str,
    difficulty: str = None,
    clarity: str = None,
    labels: List[str] = None,
    num_labels: int = 1,
    num_rows: int = 10,
    temperature: float = 0.9,
) -> str:
    labels = get_preprocess_labels(labels)
    base_code = f"""
# Requirements: `pip install distilabel[hf-inference-endpoints]`
import os
import random
from distilabel.llms import InferenceEndpointsLLM
from distilabel.pipeline import Pipeline
from distilabel.steps import LoadDataFromDicts, KeepColumns
from distilabel.steps.tasks import {"GenerateTextClassificationData" if num_labels == 1 else "GenerateTextClassificationData, TextClassification"}

MODEL = "{MODEL}"
BASE_URL = "{BASE_URL}"
TEXT_CLASSIFICATION_TASK = "{system_prompt}"
os.environ["API_KEY"] = (
    "hf_xxx"  # https://huggingface.co/settings/tokens/new?ownUserPermissions=repo.content.read&ownUserPermissions=repo.write&globalPermissions=inference.serverless.write&canReadGatedRepos=true&tokenType=fineGrained
)

with Pipeline(name="textcat") as pipeline:

    task_generator = LoadDataFromDicts(data=[{{"task": TEXT_CLASSIFICATION_TASK}}])

    textcat_generation = GenerateTextClassificationData(
        llm=InferenceEndpointsLLM(
            model_id=MODEL,
            base_url=BASE_URL,
            api_key=os.environ["API_KEY"],
            generation_kwargs={{
                "temperature": {temperature},
                "max_new_tokens": 2048,
                "do_sample": True,
                "top_k": 50,
                "top_p": 0.95,
            }},
        ),
        seed=random.randint(0, 2**32 - 1),
        difficulty={None if difficulty == "mixed" else repr(difficulty)},
        clarity={None if clarity == "mixed" else repr(clarity)},
        num_generations={num_rows},
        output_mappings={{"input_text": "text"}},
    )
    """

    if num_labels == 1:
        return (
            base_code
            + """
    keep_columns = KeepColumns(
        columns=["text", "label"],
    )

    # Connect steps in the pipeline
    task_generator >> textcat_generation >> keep_columns

    if __name__ == "__main__":
        distiset = pipeline.run()
    """
        )

    return (
        base_code
        + f"""
    keep_columns = KeepColumns(
        columns=["text"],
    )

    textcat_labeller = TextClassification(
        llm=InferenceEndpointsLLM(
            model_id=MODEL,
            base_url=BASE_URL,
            api_key=os.environ["API_KEY"],
            generation_kwargs={{
                "temperature": 0.8,
                "max_new_tokens": 2048,
            }},
        ),
        n={num_labels},
        available_labels={labels},
        context=TEXT_CLASSIFICATION_TASK,
        default_label="unknown"
    )

    # Connect steps in the pipeline
    task_generator >> textcat_generation >> keep_columns >> textcat_labeller

    if __name__ == "__main__":
        distiset = pipeline.run()
    """
    )
