# Frozen RAG context — What are the components of a time series?

_query: What are the components of a time series? trend seasonality cyclical irregular_
_books: cerqueira, spark_ts, pesaran · top_k=8 · rerank=False · 8 sources_

[1] Deep Learning for Time Series Cookbook: Use PyTorch and Python to Forecast, Classify, and Detect Anomalies — Getting ready Getting ready (authors: Cerqueira et al.; pages None-None)
A time series is composed of three parts – trend, seasonality, and the remainder:

- The trend characterizes the long-term change in the level of a time series. Trends can be upward (increase in level) or downward (decrease in level), and they can also change over time.
- Seasonality refers to regular variations in fixed periods, such as every day. The solar radiation time series plotted in the preceding recipe shows a clear yearly seasonality. Solar radiation is higher during summer and lower during winter.
- The remainder (also called irregular) of the time series is what is left after removing the trend and seasonal components.

Breaking a time series into its components is useful to understand the underlying structure of the data.

We’ll describe the process of time series decomposition with two methods: the classical decomposition approach and a method based on local regression. You’ll also learn how to extend the latter method to time series with multiple seasonal patterns.

---

[2] Time Series Analysis with Spark: A practical guide to processing, modeling, and forecasting time series with Apache Spark — Additive or multiplicative Additive or multiplicative (authors: Ramaswami; pages None-None)
Time series can be **additive** (the preceding formula) or **multiplicative**. In the first case, the seasonality and residual components are not dependent on the trend. In the second case, they change with the trend and can be seen as changing amplitude of the seasonal component – for example, higher peaks and lower troughs.

Now that we have gone through the components of time series, let’s put this into practice with code.

---

[3] Deep Learning for Time Series Cookbook: Use PyTorch and Python to Forecast, Classify, and Detect Anomalies — How it works… How it works… (authors: Cerqueira et al.; pages None-None)
In a given time step **i**, the value of the time series (**Y**i) can be decomposed using an additive model, as follows:

*Y*i *=* *Trend*i*+Seasonality*i*+Remainder*i

This decomposition can also be multiplicative:

*Y*i *=* *Trend*i*×Seasonality*i*×Remainder*i

The most appropriate approach, additive or multiplicative, depends on the input data. But you can turn a multiplicative decomposition into an additive one by transforming the data with the logarithm function. The logarithm stabilizes the variance, thus making the series additive regarding its components.

The results of the classical decomposition are shown in the following figure:

![Figure 1.3: Time series components after decomposition with the classical method](markdown/Deep Learning for Time Series Cookbook_ Use PyTorch and -- Vitor Cerqueira & Luís Roque -- 2024 -- Packt Publishing Pvt Ltd -- 36798e5b9c4126281a1cf569f366b397 -- Anna’s Archive/media/OEBPS/image/B21145_01_003.jpg)

Figure 1.3: Time series components after decomposition with the classical method

In the classical decomposition, the trend is estimated using a moving average, for example, the average of the last 24 hours (for hourly series). Seasonality is estimated by averaging the values of each period. **STL** is a more flexible method for decomposing a time series. It can handle complex patterns, such as irregular trends or outliers. **STL** leverages **LOESS**, which stands for **locally weighted scatterplot smoothing**, to extract each component.

---

[4] Time Series and Panel Data Econometrics — 12.5 Classical decomposition of time series 12.5 Classical decomposition of time series (authors: Pesaran; pages None-None)
One important aim of time series analysis is to decompose a series into a number of components that can be associated with different types of temporal variations. Time series are often governed by the following four main components:

– long term *trend*

– *seasonal* component

– *cyclical* component

– *residual* component.

These four components are usually combined together using either an additive or a multiplicative model. The latter is often transformed into an additive structure using the log-transformation. Most statistical procedures are concerned with modelling of the cyclical component and usually take trend and seasonal patterns as given or specified *a priori* by the investigator. Further discussion can be found in Mills ([1990](#050_BM_bibliographyGroup.xhtml#acprof-9780198759980-bibliography-1-bibItem-691), [2003](#050_BM_bibliographyGroup.xhtml#acprof-9780198759980-bibliography-1-bibItem-692)).

The meaning and the importance of stationarity can be appreciated in the context of the famous decomposition theorem due to Wold ([1938](#050_BM_bibliographyGroup.xhtml#acprof-9780198759980-bibliography-1-bibItem-981)). Wold proved that any stationary process can be decomposed into the sum of a deterministic (perfectly predictable) and a purely non-deterministic (stochastic) component. More formally

**Theorem 42** (Wold’s decomposition) *Any trend-stationary process* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6650.gif) *can be represented in the form of*

![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6651.gif)

*where* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6652.gif) *and* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6653.gif) *. The term* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6654.gif) *is a deterministic component, while* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6655.gif) *is a serially uncorrelated process defined by innovations in* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6656.gif)

![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6657.gif)

*where* ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6658.gif) .

In the above decomposition, ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6659.gif) is the error in the one step ahead forecast of ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6660.gif), and is also known as the ‘innovation error’. As noted in Definition 17, the deterministic component, ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6661.gif), is also known as the perfectly predictable component of ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6662.gif), in the sense that ![image](markdown/Time Series and Panel Data Econometrics/media/images/acprof-9780198759980-math-6663.gif) . Further discussion on Wold’s decomposition theorem can be found in Nerlove, Grether, and Carvalo ([1979](#050_BM_bibliographyGroup.xhtml#acprof-9780198759980-bibliography-1-bibItem-726)) and in Brockwell and Davis ([1991](#050_BM_bibliographyGroup.xhtml#acprof-9780198759980-bibliography-1-bibItem-161)).

---

[5] Deep Learning for Time Series Cookbook: Use PyTorch and Python to Forecast, Classify, and Detect Anomalies — Decomposing a time series Decomposing a time series (authors: Cerqueira et al.; pages None-None)
Time series decomposition is the process of splitting a time series into its basic components, such as trend or seasonality. This recipe explores different techniques to solve this task and how to choose among them.

---

[6] Time Series Analysis with Spark: A practical guide to processing, modeling, and forecasting time series with Apache Spark — Systematic and non-systematic components Systematic and non-systematic components (authors: Ramaswami; pages None-None)
The level, trend, seasonality, and cycle are called the **systematic** components. They represent the underlying structure of the time series, which can be modeled and hence forecast.

In addition to the systematic components, there is a **non-systematic** part that cannot be modeled, which is called residual, noise, or error. The goal of time series modeling is to find the model with the best match for the systematic components while minimizing the residuals.

We will now go into the details of each of the systematic and non-systematic parts.

---

[7] Deep Learning for Time Series Cookbook: Use PyTorch and Python to Forecast, Classify, and Detect Anomalies — Getting ready Getting ready (authors: Cerqueira et al.; pages None-None)
We learned about time series decomposition methods in [*Chapter 1*](#B21145_01.xhtml#_idTextAnchor019). Decomposition methods aim at extracting the individual parts that make up a time series.

We can use this approach to deal with seasonality. The idea is to separate the seasonal component from the rest (trend plus residuals). We can use a deep neural network to model the seasonally adjusted series. Then, we use a simple model to forecast the seasonal component.

Again, we’ll start with the daily solar radiation time series. This time, we won’t split training and testing to show how the forecasts are obtained in practice.

---

[8] Time Series Analysis with Spark: A practical guide to processing, modeling, and forecasting time series with Apache Spark — Decomposition Decomposition (authors: Ramaswami; pages None-None)
As introduced in [*Chapter 1*](#B18568_01.xhtml#_idTextAnchor016), decomposition breaks down the time series into its fundamental components: trend, seasonality, and residuals. This separation helps uncover underlying patterns within the data more clearly. The trend shows long-term movement, while seasonal components show repeating patterns. Residuals highlight any deviation from the trend and seasonal components. This decomposition allows for each component to be analyzed and addressed individually.

The following code extract shows the decomposition of time series using **seasonal_decompose** from the **statsmodels** library. In [*Chapter 1*](#B18568_01.xhtml#_idTextAnchor016), we used a different library, **Prophet**.

``` source-code
