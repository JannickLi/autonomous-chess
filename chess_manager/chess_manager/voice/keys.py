import os


def get_mistral_api_key():
    return os.getenv("MISTRAL_API_KEY", "")


def get_wandb_api_key():
    return os.getenv("WANDB_API_KEY", "")


def get_elevenlabs_api_key():
    return os.getenv("ELEVENLABS_API_KEY", "")
