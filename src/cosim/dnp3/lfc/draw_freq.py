import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

sns.set_theme(style="whitegrid", context="paper")
sns.set_palette(sns.color_palette("hsv", 10))

def draw_freq(freqs):
    timestep = 0.1
    time = np.arange(0, freqs.shape[1] * timestep, timestep)[:freqs.shape[1]]
    plt.figure(figsize=(6, 4))
    for i in range(freqs.shape[0]):
        sns.lineplot(x=time, y=freqs[i, :], label=f"Freq {i+1}", linewidth=1.5)
    plt.xlabel('Time (s)', fontsize=10)
    plt.ylabel('Frequency (Hz)', fontsize=10)
    plt.title('Frequency vs Time', fontsize=12)
    plt.tight_layout()
    plt.show()

with open('./src/logs/freqs.log') as f:
    freqs = [line.strip().split(",") for line in f.readlines()]
    freqs = np.array(freqs, dtype=float).T
    draw_freq(freqs)