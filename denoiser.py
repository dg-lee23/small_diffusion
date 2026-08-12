import math
import torch
import torch.nn as nn

class GAS_Denoiser(nn.Module):

    def __init__(self, dim=2, time_emb_dim=64, hidden=128, n_layers=3):
        super().__init__()
        self.dim = dim
        self.time_emb_dim = time_emb_dim
        self.hidden = hidden
        self.n_layers = n_layers

        # time embedding
        self.time_mlp = nn.Sequential(
            nn.Linear(time_emb_dim, time_emb_dim),
            nn.SiLU(),
            nn.Linear(time_emb_dim, time_emb_dim)
        )

        # MLP
        layers = [nn.Linear(self.dim + self.time_emb_dim, self.hidden), nn.SiLU()]
        for _ in range(self.n_layers):
          layers.append(nn.Linear(self.hidden, self.hidden))
          layers.append(nn.SiLU())
        layers.append(nn.Linear(self.hidden, self.dim))
        self.net = nn.Sequential(*layers)

    def sinusoidal_embedding(self, t, dim):
        # t: (B,)  ->  (B, dim)
        half = dim // 2   # ex. dim=64, half=32
        freqs = torch.exp(-math.log(10000) * torch.arange(half, device=t.device) / (half - 1))        #  exp [0.001 * [0, 1/32, ..., 1]],  1 -> 1/10000 감소하는 주파수
        args = t.float().unsqueeze(-1) * freqs.unsqueeze(0)   # (B, 1) * (1, half) = (B, half)
        return torch.cat([torch.sin(args), torch.cos(args)], dim=-1)  # (B, dim)

    def forward(self, x_t, t):
        """x_t: (B, D)  t: (B,)
        returns eps_pred: (B, D)"""
        t_embed = self.sinusoidal_embedding(t, self.time_emb_dim)    # (B, time_emb_dim)
        t_embed = self.time_mlp(t_embed)                             # (B, time_emb_dim)
        h = torch.cat([x_t, t_embed], dim=1)                         # (B, D + time_emb_dim)
        eps_pred = self.net(h)
        return eps_pred