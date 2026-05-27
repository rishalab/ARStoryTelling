'''
a python function which uses the inference command for the rigging_model and the output is send to another model

cmd = [
    "bash",
    "scripts/inference.sh",
    "data_examples/spyro_the_dragon.glb",
    "1",
    "8192"
]

result = subprocess.run(
    cmd,
    cwd="/absolute/path/to/services/rigging/rigging_model",
    capture_output=True,
    text=True
)

print(result.stdout)
print(result.stderr)

something like this
sh scripts/inference.sh data_examples/spyro_the_dragon.glb 1 8192 -> inference command


'''