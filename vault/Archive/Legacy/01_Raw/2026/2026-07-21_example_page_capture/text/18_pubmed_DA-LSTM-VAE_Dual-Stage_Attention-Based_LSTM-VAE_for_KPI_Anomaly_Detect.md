---
title: "DA-LSTM-VAE: Dual-Stage Attention-Based LSTM-VAE for KPI Anomaly Detection."
type: raw-text
connector: pubmed
status: ready
created: 2026-07-21
tags:
  - type/raw-text
  - source/pubmed
  - topic/example_page_capture
keywords:
  - "example"
  - "page"
  - "capture"
url: "https://pubmed.ncbi.nlm.nih.gov/36359702/"
authors: "Yun Zhao, Xiuguo Zhang, Zijing Shang, Zhiying Cao"
published: 2022-11-05
---

# DA-LSTM-VAE: Dual-Stage Attention-Based LSTM-VAE for KPI Anomaly Detection.

- 原文: https://pubmed.ncbi.nlm.nih.gov/36359702/

> [!quote] 原始文字
>
> DA-LSTM-VAE: Dual-Stage Attention-Based LSTM-VAE for KPI Anomaly Detection.
> Journal: Entropy (Basel, Switzerland)
>
> To ensure the normal operation of the system, the enterprise's operations engineer will monitor the system through the KPI (key performance indicator). For example, web page visits, server memory utilization, etc. KPI anomaly detection is a core technology, which is of great significance for rapid fault detection and repair. This paper proposes a novel dual-stage attention-based LSTM-VAE (DA-LSTM-VAE) model for KPI anomaly detection. Firstly, in order to capture time correlation in KPI data, long-short-term memory (LSTM) units are used to replace traditional neurons in the variational autoencoder (VAE). Then, in order to improve the effect of KPI anomaly detection, an attention mechanism is introduced into the input stage of the encoder and decoder, respectively. During the input stage of the encoder, a time attention mechanism is adopted to assign different weights to different time points, which can adaptively select important input sequences to avoid the influence of noise in the data. During the input stage of the decoder, a feature attention mechanism is adopted to adaptively select important latent variable representations, which can capture the long-term dependence of time series better. In addition, this paper proposes an adaptive threshold method based on anomaly scores measured by reconstruction probability, which can minimize false positives and false negatives and avoid adjustment of the threshold manually. Experimental results in a public dataset show that the proposed method in this paper outperforms other baseline methods.

## 关键词

example, page, capture
