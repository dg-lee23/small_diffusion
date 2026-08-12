import torch
import math

class GAS_NoiseScheduler:
    def __init__(self, T=1000, beta_start=1e-4, beta_end=0.02):

        self.betas = torch.linspace(beta_start, beta_end, T)
        self.alphas = 1 - self.betas
        self.alpha_bars = torch.cumprod(self.alphas, dim=0)

        self.sqrt_alpha_bars = torch.sqrt(self.alpha_bars)
        self.sqrt_one_minus_alpha_bars = torch.sqrt(1 - self.alpha_bars)
        self.recip_sqrt_alphas = 1 / torch.sqrt(self.alphas)
        self.eps_pred_weight = (1 - self.alphas) / self.sqrt_one_minus_alpha_bars

        self.sigmas = torch.sqrt(self.betas)

    def add_noise(self, x0, noise, t):

        a = self.sqrt_alpha_bars[t].view(-1, 1)
        b = self.sqrt_one_minus_alpha_bars[t].view(-1, 1)

        x_t = a * x0 +  b * noise    # (B, 1) * (B, D) broadcasts
        return x_t

    def step(self, eps_pred, t, x_t):

        noise = torch.randn_like(x_t)        # (B, D)
        t_mask = (t > 0).float().view(-1, 1)
        recip_sqrt_alphas = self.recip_sqrt_alphas[t].view(-1,1)


        x_prev = recip_sqrt_alphas * (x_t - self.eps_pred_weight[t].view(-1, 1) * eps_pred)     \
                                                + t_mask * self.sigmas[t].view(-1,1) * noise    # (B, 1) * (B, D) + (B, 1) * (B, D)

        return x_prev
