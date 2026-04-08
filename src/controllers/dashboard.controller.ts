import { Request, Response, NextFunction } from 'express';
import { AnalyticsService } from '../services/analytics.service';
import { TransactionType } from '@prisma/client';

const service = new AnalyticsService();

export const getSummary = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;

    const summary = await service.getSummary(userId, userRole);
    res.status(200).json({
      status: 'success',
      data: summary,
    });
  } catch (error) {
    next(error);
  }
};

export const getCategoryBreakdown = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const type = req.query.type as TransactionType | undefined;

    const breakdown = await service.getCategoryBreakdown(userId, userRole, type);
    res.status(200).json({
      status: 'success',
      data: breakdown,
    });
  } catch (error) {
    next(error);
  }
};

export const getMonthlyTrend = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const year = Number(req.query.year) || new Date().getFullYear();

    const trend = await service.getMonthlyTrend(userId, userRole, year);
    res.status(200).json({
      status: 'success',
      data: trend,
    });
  } catch (error) {
    next(error);
  }
};

export const getRecentActivity = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const limit = Number(req.query.limit) || 10;

    const activity = await service.getRecentActivity(userId, userRole, limit);
    res.status(200).json({
      status: 'success',
      data: activity,
    });
  } catch (error) {
    next(error);
  }
};

export const getTopCategories = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userRole = req.user!.role;
    const userId = req.user!.sub;
    const limit = Number(req.query.limit) || 5;

    const topCategories = await service.getTopCategories(userId, userRole, limit);
    res.status(200).json({
      status: 'success',
      data: topCategories,
    });
  } catch (error) {
    next(error);
  }
};
