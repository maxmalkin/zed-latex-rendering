# %% [markdown]
# # Package-aware notebook
#
# This Markdown equation uses the local package: $\LocalSet$.

# %%
from zed_latex import tex
tex(r"\LocalSet")

# %%
print("This output is included when you run all cells and export.")
