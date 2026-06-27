package com.demo.repository;

@Repository
public interface UserRepository {
    String findById(String id);
}
