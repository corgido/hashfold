# Working with deterministic measurement pipelines

This guide explains how to integrate a deterministic measurement
pipeline into a content moderation workflow. The instructions below
assume you have already installed the relevant packages and have
access to the configuration files described in the previous section.

## Overview

A deterministic measurement pipeline is a system that produces
identical outputs for identical inputs, regardless of when or where
it is run. This property is important when you need to verify that
the same content has been processed the same way across different
deployments, or when you need to compare results from different time
periods.

The pipeline takes a text input and produces a structured output
containing several types of measurements:

- Surface-level metrics, such as word counts, sentence counts, and
  punctuation densities
- Lexical metrics, such as type-token ratios and lexical diversity
  scores
- Discourse-level metrics, such as the density of contrast markers
  and elaboration cues
- Trajectory metrics, which describe how these properties change
  across the document

You can think of the output as a fingerprint of the input text. Two
texts with similar fingerprints share similar surface properties.
The pipeline does not interpret these properties; it only measures
them.

## Setting up your environment

Before running the pipeline, ensure that your environment meets the
following requirements. The pipeline depends only on the standard
library, so installation is typically straightforward. You will need
Python 3.10 or later, which most modern systems already have.

To verify your installation, run the test suite:

```
pytest instrument/
```

If all tests pass, your environment is correctly configured. If any
tests fail, consult the troubleshooting guide before proceeding.

## Basic usage

The simplest way to use the pipeline is through the command-line
interface. Given a text file, the CLI prints the measurement output
as JSON to standard output. For example:

```
python run.py document.md
```

This will produce a JSON object with the structure described in the
API reference. The output is deterministic: running the same command
on the same file at any point in the future will produce
byte-identical output, provided the pipeline version has not changed.

If you need to integrate the pipeline into a larger workflow, you
can run it as an HTTP server instead. The server accepts POST
requests with the text to measure as the request body, and returns
the measurement as a JSON response.

```
python -m instrument.serve.http &
curl -X POST --data-binary @document.md http://localhost:8000/
```

The server is stateless; each request is processed independently of
all other requests. This makes the pipeline suitable for use behind
a load balancer.

## Output shape

By default, the server returns an abbreviated output suitable for
real-time use. If you need the full measurement output, you can
request it by passing a query parameter:

```
curl -X POST --data-binary @document.md \
  'http://localhost:8000/?shape=audit'
```

The audit shape includes all measurements, all reference distances,
and the full provenance metadata. It is the recommended shape for
compliance pipelines.

## Interpreting the output

The pipeline does not interpret its measurements. This is by design;
interpretation requires choices about what counts as significant,
and those choices should be made by the consumer of the
measurements, not by the pipeline itself.

That said, there are some general patterns that may help you make
sense of the output:

- A high **type-token ratio** indicates lexical diversity. Documents
  with many unique words score higher.
- A high **modal density** indicates frequent use of words like
  "may", "might", "could", and so on. This is sometimes associated
  with hedging.
- A high **contrast density** indicates frequent use of contrast
  markers like "however", "but", and "although". This is sometimes
  associated with argumentative writing.

These associations are heuristic, not definitive. The pipeline
reports the measurements; what they mean for your application
depends on what your application is trying to achieve.

## Versioning

Each measurement output is stamped with the version of the pipeline
that produced it. If you store the measurements alongside the
inputs, you can verify later that a given measurement was produced
by a known pipeline version, even if the pipeline has been updated
in the meantime.

The version is reported in the metadata block of the output:

```
"metadata": {
  "instrument_version": "0.7.0",
  "lexicon_version": "v1",
  "catalog_sha256": "...",
  ...
}
```

If you need to verify the integrity of a stored measurement, you
can re-run the pipeline against the same input and compare the
outputs. Provided the pipeline version has not changed, the
outputs should be byte-identical except for the timestamp field,
which records when the measurement was made.

## Best practices

When integrating the pipeline into a workflow, consider the
following:

- Pin the pipeline version. Use the version reported in the
  metadata block, and re-pin only when you have verified that the
  new version produces equivalent measurements on a representative
  sample of your data.
- Store the raw measurement output, not just a summary or a
  derived score. The raw output is the canonical record; any
  summary you compute is a downstream artefact.
- Compute your own thresholds. If you need to flag certain
  measurements as significant, do this on top of the pipeline's
  output, using thresholds that you have validated against your
  own data.

These practices apply equally whether you are using the pipeline
for compliance recording, for content classification, or for any
other purpose. The pipeline's job is to provide the measurements;
your job is to decide what to do with them.
