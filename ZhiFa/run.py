#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
智法AI - 应用启动入口

使用方法：
    python run.py
"""
import os

# Set environment variable to prevent PaddleX crash during model source check
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'

if __name__ == '__main__':
    from src.app import run_app
    run_app()

