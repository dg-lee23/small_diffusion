from denoiser import GAS_Denoiser
from scheduler import GAS_NoiseScheduler
from torch.utils.data import TensorDataset, DataLoader
import numpy as np
import torch
import matplotlib.pyplot as plt
from tqdm import tqdm

# 1. 데이터 준비
# load data 
data = np.load('GAS.npy')
data_tensor = torch.tensor(data, dtype=torch.float32)

# split data, 8:1:1
n_samples = len(data_tensor)
train_end = int(n_samples * 0.8)
val_end = int(n_samples * 0.9)

train_data = data_tensor[:train_end]
val_data = data_tensor[train_end : val_end]
test_data = data_tensor[val_end:]

# put into DataLoader
train_loader = DataLoader(TensorDataset(train_data), batch_size = 128, shuffle=True)
val_loader = DataLoader(TensorDataset(val_data), batch_size = 128, shuffle=True)



# 2. 모델 준비
data_dim = data_tensor.shape[-1]
model = GAS_Denoiser(dim=data_dim, time_emb_dim=64, hidden=128, n_layers=3)
scheduler = GAS_NoiseScheduler(T=1000, beta_start=1e-4, beta_end=0.02)

opt = torch.optim.Adam(model.parameters(), lr=1e-4)
epochs = 200
epoch_losses = []



# 3. 학습
for epoch in tqdm(range(epochs)):
    batch_losses = []

    for (batch_X, ) in train_loader:

        x_0 = batch_X # (B, D)
        B = x_0.shape[0]
        T = len(scheduler.betas)
        t = torch.randint(0, T, (B, )) 
        noise = torch.randn_like(x_0)

        x_t = scheduler.add_noise(x_0, noise, t)
        eps_pred = model(x_t, t)
        loss = ((eps_pred - noise)**2).mean()  
        batch_losses.append(loss.detach().numpy())

        opt.zero_grad()
        loss.backward()
        opt.step()

    print(sum(batch_losses)/len(batch_losses))
    epoch_losses.append(sum(batch_losses)/len(batch_losses))



plt.plot(epoch_losses)