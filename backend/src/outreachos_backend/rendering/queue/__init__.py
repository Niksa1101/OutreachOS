"""Worker pool and job state machine.

Concurrency is pinned to 1 in V1. The pool abstraction exists so that parallel
rendering is a configuration change rather than a rewrite.

Six states: waiting -> preparing -> rendering -> encoding -> completed | failed.
A job failure never stops the batch.
"""
