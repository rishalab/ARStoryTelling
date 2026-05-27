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

Outputs
Results are written under outputs/<asset_name>/ with these key files:

<name>_simplified.glb: the simplified input mesh used for inference
<name>_simplified.npz: intermediate results (joints, weights, etc.)
<name>_simplified_rig.glb: the final rigged mesh you can import into Blender
inference.log: logs from all steps

but we need to return the simplified_rig as the function output

the input to the function will come from the api which is outside the side the services folder, all the async api calling will be done there. 
and we import this function in the api calling and return the output and keep the input to another model.

after completing this function, complete the README.md which is in this rigging directoty, explaining how we are connecting this to the main pipeline.
'''